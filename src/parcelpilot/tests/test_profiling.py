from __future__ import annotations

import cProfile
import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import profiling.capture as capture
from profiling.capture import (
    capture_pyspy,
    parse_collapsed_stacks,
    write_cprofile_artifacts,
    write_sampled_artifacts,
)


def _profiled_leaf() -> None:
    return None


def _profiled_work() -> None:
    for _ in range(3):
        _profiled_leaf()


def test_parse_collapsed_stacks_validates_and_splits_frames() -> None:
    stacks = parse_collapsed_stacks(["root;module.py:12:work 3\n", "\n"])

    assert len(stacks) == 1
    assert stacks[0].frames == ("root", "module.py:12:work")
    assert stacks[0].samples == 3


def test_parse_collapsed_stacks_preserves_samples_without_python_frames() -> None:
    stacks = parse_collapsed_stacks(["1\n"])

    assert len(stacks) == 1
    assert stacks[0].frames == ("[no Python frames]",)
    assert stacks[0].samples == 1


@pytest.mark.parametrize("line", ["root", "root;leaf 0", "root;;leaf 2", "root;leaf -1"])
def test_parse_collapsed_stacks_rejects_invalid_lines(line: str) -> None:
    with pytest.raises(ValueError):
        parse_collapsed_stacks([line])


def test_sampled_artifacts_create_speedscope_flamegraph_and_deduplicated_totals(
    tmp_path: Path,
) -> None:
    collapsed = tmp_path / "stacks.collapsed"
    collapsed.write_text(
        "module.py:10:work;module.py:10:work;module.py:20:leaf 2\n"
        "module.py:10:work;module.py:30:other 1\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "pyspy"

    functions_path = write_sampled_artifacts(collapsed, output_dir, sample_rate=10)

    speedscope = json.loads((output_dir / "speedscope.json").read_text(encoding="utf-8"))
    assert speedscope["profiles"][0]["endValue"] == pytest.approx(0.3)
    assert len(speedscope["profiles"][0]["samples"]) == 3
    svg = (output_dir / "flamegraph.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg ")
    with functions_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    work = next(row for row in rows if row["function"] == "work")
    assert float(work["total_time_s"]) == pytest.approx(0.3)
    assert work["calls"] == ""


def test_cprofile_artifacts_include_total_call_counts(tmp_path: Path) -> None:
    profile = cProfile.Profile()
    profile.runcall(_profiled_work)
    profile_path = tmp_path / "profile.pstats"
    profile.dump_stats(str(profile_path))

    functions_path = write_cprofile_artifacts(profile_path, tmp_path / "functions.csv")

    with functions_path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    leaf = next(row for row in rows if row["function"] == "_profiled_leaf")
    assert leaf["calls"] == "3"


def test_pyspy_capture_passes_integer_seconds_to_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        output_index = command.index("--output") + 1
        Path(command[output_index]).write_text("module.py:10:work 1\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(capture.shutil, "which", lambda _name: "py-spy")
    monkeypatch.setattr(capture.subprocess, "run", fake_run)

    capture_pyspy(123, 300.0, tmp_path / "pyspy")

    duration_index = commands[0].index("--duration") + 1
    assert commands[0][duration_index] == "300"


def test_pyspy_capture_rejects_fractional_seconds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(capture.shutil, "which", lambda _name: "py-spy")

    with pytest.raises(ValueError, match="whole number"):
        capture_pyspy(123, 1.5, tmp_path / "pyspy")
