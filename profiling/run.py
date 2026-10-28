from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib.metadata
import json
import os
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

from profiling.capture import capture_pyspy, write_cprofile_artifacts

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEFAULT_LOCUSTFILE = ROOT / "profiling" / "scenarios" / "locustfile.py"
SEED_PREFIX = "/api/v1/_seed"
SEED_DOMAINS = [
    "warehouses",
    "categories",
    "products",
    "stock",
    "customers",
    "orders",
    "fraud",
    "search",
    "tax",
    "discounts",
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the service and capture a profile.")
    parser.add_argument("--workload", choices=("benign", "typical", "hostile"), required=True)
    parser.add_argument("--scale", type=float, required=True)
    parser.add_argument("--duration", type=float, default=300)
    parser.add_argument("--profiler", choices=("pyspy", "cprofile"), default="pyspy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--locustfile", type=Path, default=DEFAULT_LOCUSTFILE)
    parser.add_argument("--warmup-duration", type=float, default=60)
    parser.add_argument("--startup-timeout", type=float, default=60)
    parser.add_argument("--seed-timeout", type=float, default=3600)
    parser.add_argument("--seed-stall-timeout", type=float, default=60)
    parser.add_argument("--sample-rate", type=int, default=100)
    parser.add_argument("--artifacts-dir", type=Path, default=ROOT / "profiles")
    return parser


def _check_args(args: argparse.Namespace) -> None:
    if not 0.01 <= args.scale <= 1.0:
        raise ValueError("--scale must be between 0.01 and 1.0")
    if args.duration <= 0 or args.warmup_duration < 0:
        raise ValueError(
            "--duration must be positive and --warmup-duration cannot be negative"
        )
    if args.profiler == "pyspy" and not float(args.duration).is_integer():
        raise ValueError("--duration must be a whole number of seconds when using pyspy")
    if args.startup_timeout <= 0 or args.seed_timeout <= 0 or args.seed_stall_timeout <= 0:
        raise ValueError("Startup and seed timeouts must be positive")
    if args.sample_rate <= 0:
        raise ValueError("--sample-rate must be positive")
    if not args.locustfile.is_file():
        raise FileNotFoundError(
            f"Locust scenario file not found: {args.locustfile}. "
            "The scenario suite is provided by the human-like scenarios task."
        )
    if args.profiler == "pyspy" and os.name == "nt":
        raise RuntimeError(
            "py-spy process attachment is supported on Linux and macOS, not Windows"
        )
    if shutil.which("locust") is None:
        raise RuntimeError(
            "Locust is required for profile scenarios; install the pinned project dependency"
        )
    if args.profiler == "pyspy" and shutil.which("py-spy") is None:
        raise RuntimeError(
            "py-spy is required for profiler=pyspy; install the pinned project dependency"
        )


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(SRC) if not existing_path else os.pathsep.join((str(SRC), existing_path))
    )
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run_checked(
    command: Sequence[str],
    *,
    env: dict[str, str],
    timeout: float | None = None,
) -> None:
    result = subprocess.run(
        list(command),
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        rendered_command = " ".join(command)
        raise RuntimeError(f"Command failed ({rendered_command}): {detail}")


def _wait_for_postgres(env: dict[str, str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_detail = "no response"
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "pg_isready",
                "-U",
                "postgres",
                "-d",
                "parcelpilot",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return
        last_detail = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"exit code {result.returncode}"
        )
        time.sleep(2)
    raise TimeoutError(
        f"PostgreSQL did not become ready within {timeout:g} seconds: {last_detail}"
    )


def _api_url(host: str, port: int, path: str) -> str:
    return f"http://{host}:{port}{path}"


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    seed_key: str,
    timeout: float = 30,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"X-Seed-Key": seed_key}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            decoded = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Seed API request {method} {url} returned HTTP {error.code}: {detail}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Seed API request {method} {url} failed: {error.reason}") from error
    if not decoded:
        return {}
    result = json.loads(decoded)
    if not isinstance(result, dict):
        raise RuntimeError(f"Seed API request {method} {url} returned a non-object response")
    return result


def _wait_for_api(
    host: str,
    port: int,
    process: subprocess.Popen[str],
    timeout: float,
    log_path: Path,
) -> None:
    url = _api_url(host, port, "/health")
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "API process exited during startup with code "
                f"{process.returncode}:\n{_read_tail(log_path)}"
            )
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and payload.get("db") == "ok":
                return
            last_error = f"health response was {payload!r}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = str(error)
        time.sleep(1)
    raise TimeoutError(
        f"API did not become ready within {timeout:g} seconds: {last_error}\n"
        f"{_read_tail(log_path)}"
    )


def _stop_process(process: subprocess.Popen[str], *, graceful: bool = True) -> None:
    if process.poll() is not None:
        return
    if graceful and os.name == "nt":
        process.send_signal(signal.CTRL_C_EVENT)
    else:
        process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _read_tail(path: Path, limit: int = 4000) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(max(0, path.stat().st_size - limit))
        return handle.read()


def _run_locust(
    args: argparse.Namespace,
    env: dict[str, str],
    *,
    base_url: str,
    run_time: float,
    username: str,
    password: str,
    seed_key: str,
    log_path: Path,
    csv_prefix: Path | None = None,
) -> subprocess.Popen[str]:
    locust = shutil.which("locust")
    if locust is None:
        raise RuntimeError("Locust disappeared from PATH after preflight")
    command = [
        locust,
        "--locustfile",
        str(args.locustfile.resolve()),
        "--host",
        base_url,
        "--headless",
        "--users",
        "20",
        "--spawn-rate",
        str(1 / 3),
        "--run-time",
        f"{run_time:g}s",
        "--stop-timeout",
        "10",
        "--only-summary",
    ]
    if csv_prefix is not None:
        command.extend(["--csv", str(csv_prefix)])
    scenario_env = env.copy()
    scenario_env.update(
        {
            "PARCELPILOT_BASE_URL": base_url,
            "PARCELPILOT_TENANT_SLUG": "acme",
            "PARCELPILOT_USERNAME": username,
            "PARCELPILOT_PASSWORD": password,
            "PARCELPILOT_SEED_KEY": seed_key,
            "PARCELPILOT_WORKLOAD": args.workload,
        }
    )
    with log_path.open("w", encoding="utf-8") as log_file:
        return subprocess.Popen(
            command,
            cwd=ROOT,
            env=scenario_env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )


def _wait_for_locust(process: subprocess.Popen[str], run_time: float, log_path: Path) -> None:
    try:
        process.wait(timeout=run_time + 90)
    except subprocess.TimeoutExpired:
        _stop_process(process, graceful=False)
        raise TimeoutError("Locust did not finish within the configured run time")
    if process.returncode:
        raise RuntimeError(
            f"Locust exited with code {process.returncode}:\n{_read_tail(log_path)}"
        )


def _wait_for_seed_job(
    job_id: int,
    *,
    host: str,
    port: int,
    seed_key: str,
    timeout: float,
    stall_timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    url = _api_url(host, port, f"{SEED_PREFIX}/jobs/{job_id}")
    last_status = "unknown"
    last_observation: tuple[str, str, str] | None = None
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        job = _request_json(url, seed_key=seed_key)
        last_status = str(job.get("status", "unknown"))
        if last_status == "completed":
            return job
        if last_status in {"failed", "cancelled"}:
            raise RuntimeError(f"Seed job {job_id} ended with status {last_status}: {job!r}")
        observation = (
            last_status,
            json.dumps(job.get("progress"), sort_keys=True),
            str(job.get("updated_at", "")),
        )
        if observation != last_observation:
            last_observation = observation
            last_change = time.monotonic()
        elif time.monotonic() - last_change >= stall_timeout:
            raise TimeoutError(
                f"Seed job {job_id} made no progress for {stall_timeout:g} seconds; "
                f"last status was {last_status}"
            )
        time.sleep(2)
    raise TimeoutError(
        f"Seed job {job_id} did not complete within {timeout:g} seconds; "
        f"last status was {last_status}"
    )


def _csv_text(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Locust did not produce the expected artifact: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _locust_summary(locust_dir: Path) -> tuple[dict[str, int], int, int, float]:
    stats_path = locust_dir / "stats.csv"
    failures_path = locust_dir / "failures.csv"
    stats = _csv_text(stats_path)
    endpoint_hits: dict[str, int] = {}
    requests = 0
    failures = 0
    for row in stats:
        name = row.get("Name", "")
        if name and name.lower() != "aggregated":
            try:
                count = int(row.get("Request Count", "0"))
                failed_count = int(row.get("Failure Count", "0"))
            except ValueError as error:
                raise ValueError(f"Invalid Locust stats row for {name!r}: {row!r}") from error
            endpoint_hits[name] = count
            requests += count
            failures += failed_count
    if failures_path.exists():
        failure_rows = _csv_text(failures_path)
        if not stats:
            failures = sum(int(row.get("Occurrences", "0")) for row in failure_rows)
    error_rate = failures / requests if requests else 0.0
    return endpoint_hits, requests, failures, error_rate


def _rename_locust_files(locust_dir: Path) -> None:
    for old_name, new_name in (
        ("locust_stats.csv", "stats.csv"),
        ("locust_failures.csv", "failures.csv"),
    ):
        old_path = locust_dir / old_name
        if old_path.exists():
            old_path.replace(locust_dir / new_name)


def _version_metadata() -> dict[str, str | None]:
    distributions = (
        "fastapi",
        "uvicorn",
        "pydantic",
        "SQLAlchemy",
        "psycopg",
        "numpy",
        "pandas",
        "locust",
    )
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for distribution in distributions:
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None
    py_spy = shutil.which("py-spy")
    if py_spy is None:
        versions["py-spy"] = None
    else:
        result = subprocess.run([py_spy, "--version"], capture_output=True, text=True, check=False)
        if result.returncode:
            raise RuntimeError(f"Could not read py-spy version: {result.stderr.strip()}")
        versions["py-spy"] = result.stdout.strip()
    return versions


def _git_sha(env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("A Git checkout is required to record the profile's source revision")
    return result.stdout.strip()


def _write_meta(
    output_path: Path,
    args: argparse.Namespace,
    *,
    start_time: dt.datetime,
    end_time: dt.datetime,
    seed_job: dict[str, Any],
    endpoint_hits: dict[str, int],
    requests: int,
    failures: int,
    error_rate: float,
    git_sha: str,
) -> None:
    profiler_flags = (
        {"format": "raw", "sample_rate_hz": args.sample_rate, "pid": "api"}
        if args.profiler == "pyspy"
        else {"mode": "cProfile.Profile", "capture_started_after_warmup": True}
    )
    payload = {
        "git_sha": git_sha,
        "workload": args.workload,
        "scale": args.scale,
        "duration_s": args.duration,
        "profiler": args.profiler,
        "profiler_flags": profiler_flags,
        "versions": _version_metadata(),
        "started_at": start_time.isoformat().replace("+00:00", "Z"),
        "finished_at": end_time.isoformat().replace("+00:00", "Z"),
        "seed_job": {
            "job_id": seed_job.get("job_id"),
            "status": seed_job.get("status"),
        },
        "endpoint_hit_counts": endpoint_hits,
        "requests": requests,
        "failures": failures,
        "error_rate": error_rate,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _start_api(
    args: argparse.Namespace,
    env: dict[str, str],
    profile_path: Path,
    log_path: Path,
) -> subprocess.Popen[str]:
    if args.profiler == "cprofile":
        command = [
            sys.executable,
            "-m",
            "profiling.serve_cprofile",
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--output",
            str(profile_path),
        ]
    else:
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "parcelpilot.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--workers",
            "1",
        ]
    options: dict[str, Any] = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    with log_path.open("w", encoding="utf-8") as log_file:
        return subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            **options,
        )


def run(args: argparse.Namespace) -> Path:
    _check_args(args)
    env = _environment()
    git_sha = _git_sha(env)
    seed_key = secrets.token_urlsafe(32)
    env.update({"SEED_ENABLED": "true", "SEED_KEY": seed_key})
    base_url = f"http://{args.host}:{args.port}"
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact_dir = args.artifacts_dir.resolve() / args.workload / timestamp
    artifact_dir.mkdir(parents=True, exist_ok=False)
    locust_dir = artifact_dir / "locust"
    locust_dir.mkdir()
    profile_dir = artifact_dir / args.profiler
    profile_dir.mkdir()
    profile_path = profile_dir / "profile.pstats"

    api_process: subprocess.Popen[str] | None = None
    locust_process: subprocess.Popen[str] | None = None
    try:
        _run_checked(["docker", "compose", "up", "-d", "postgres"], env=env, timeout=120)
        _wait_for_postgres(env, args.startup_timeout)
        _run_checked([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, timeout=300)

        api_process = _start_api(args, env, profile_path, artifact_dir / "api.log")
        _wait_for_api(
            args.host,
            args.port,
            api_process,
            args.startup_timeout,
            artifact_dir / "api.log",
        )

        _request_json(
            _api_url(args.host, args.port, f"{SEED_PREFIX}/reset"),
            method="POST",
            payload={"confirm": True},
            seed_key=seed_key,
        )
        tenant = _request_json(
            _api_url(args.host, args.port, f"{SEED_PREFIX}/tenants"),
            method="POST",
            payload={"slug": "acme", "name": "Acme"},
            seed_key=seed_key,
        )
        users = tenant.get("users", [])
        if not users or "email" not in users[0] or "password" not in users[0]:
            raise RuntimeError(
                "Tenant creation did not return the credentials required by the scenario suite"
            )
        username = str(users[0]["email"])
        password = str(users[0]["password"])
        accepted = _request_json(
            _api_url(args.host, args.port, f"{SEED_PREFIX}/workloads/{args.workload}"),
            method="POST",
            payload={
                "tenant_slug": "acme",
                "scale": args.scale,
                "domains": SEED_DOMAINS,
            },
            seed_key=seed_key,
        )
        if not accepted.get("job_id"):
            raise RuntimeError(f"Workload seeding did not return a job identifier: {accepted!r}")
        seed_job = _wait_for_seed_job(
            int(accepted["job_id"]),
            host=args.host,
            port=args.port,
            seed_key=seed_key,
            timeout=args.seed_timeout,
            stall_timeout=args.seed_stall_timeout,
        )

        if args.warmup_duration:
            warmup = _run_locust(
                args,
                env,
                base_url=base_url,
                run_time=args.warmup_duration,
                username=username,
                password=password,
                seed_key=seed_key,
                log_path=locust_dir / "warmup.log",
            )
            _wait_for_locust(warmup, args.warmup_duration, locust_dir / "warmup.log")

        if args.profiler == "cprofile":
            if api_process.poll() is not None:
                raise RuntimeError(
                    f"API process exited before capture with code {api_process.returncode}"
                )
            start_signal = getattr(signal, "SIGUSR1", None)
            if start_signal is None:
                start_signal = getattr(signal, "SIGBREAK", None)
            if start_signal is None:
                raise RuntimeError(
                    "This platform does not provide a signal for starting cProfile capture"
                )
            api_process.send_signal(start_signal)

        start_time = dt.datetime.now(dt.timezone.utc)
        csv_prefix = locust_dir / "locust"
        locust_process = _run_locust(
            args,
            env,
            base_url=base_url,
            run_time=args.duration,
            username=username,
            password=password,
            seed_key=seed_key,
            log_path=locust_dir / "run.log",
            csv_prefix=csv_prefix,
        )
        if args.profiler == "pyspy":
            capture_pyspy(
                api_process.pid,
                args.duration,
                profile_dir,
                sample_rate=args.sample_rate,
            )
        _wait_for_locust(locust_process, args.duration, locust_dir / "run.log")
        locust_process = None
        end_time = dt.datetime.now(dt.timezone.utc)
        _rename_locust_files(locust_dir)
        endpoint_hits, requests, failures, error_rate = _locust_summary(locust_dir)

        if api_process is not None:
            _stop_process(api_process)
            api_process = None
        if args.profiler == "cprofile":
            if not profile_path.exists():
                raise RuntimeError("The cProfile server stopped without writing profile.pstats")
            functions_path = write_cprofile_artifacts(profile_path, profile_dir / "functions.csv")
            (artifact_dir / "functions.csv").write_bytes(functions_path.read_bytes())
        else:
            functions_path = profile_dir / "functions.csv"
            (artifact_dir / "functions.csv").write_bytes(functions_path.read_bytes())

        _write_meta(
            artifact_dir / "meta.json",
            args,
            start_time=start_time,
            end_time=end_time,
            seed_job=seed_job,
            endpoint_hits=endpoint_hits,
            requests=requests,
            failures=failures,
            error_rate=error_rate,
            git_sha=git_sha,
        )
        return artifact_dir
    finally:
        if locust_process is not None:
            _stop_process(locust_process, graceful=False)
        if api_process is not None:
            _stop_process(api_process)


def main() -> None:
    args = _parser().parse_args()
    artifact_dir = run(args)
    print(artifact_dir)


if __name__ == "__main__":
    main()
