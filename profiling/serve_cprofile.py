from __future__ import annotations

import argparse
import asyncio
import cProfile
import signal
import threading
from pathlib import Path

import uvicorn


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the API with cProfile capture enabled on demand."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile()
    server = uvicorn.Server(
        uvicorn.Config(
            "parcelpilot.main:app",
            host=args.host,
            port=args.port,
            workers=1,
            log_level="info",
        )
    )
    profiling_started = False

    def start_profile(_signum: int, _frame: object) -> None:
        nonlocal profiling_started
        if not profiling_started:
            threading.setprofile_all_threads(profiler)
            profiler.enable()
            profiling_started = True

    start_signal = getattr(signal, "SIGUSR1", None)
    if start_signal is None:
        start_signal = getattr(signal, "SIGBREAK", None)
    if start_signal is None:
        raise RuntimeError("This platform does not provide a signal for starting cProfile capture")
    signal.signal(start_signal, start_profile)

    try:
        asyncio.run(server.serve())
    finally:
        if profiling_started:
            profiler.disable()
            threading.setprofile_all_threads(None)
            profiler.dump_stats(str(args.output))


if __name__ == "__main__":
    main()
