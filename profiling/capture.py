from __future__ import annotations

import cProfile
import csv
import json
import re
import shutil
import subprocess
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape

_COLLAPSED_LINE = re.compile(r"^(?P<stack>.+)\s+(?P<count>\d+)\s*$")
_FILE_LINE_FUNCTION = re.compile(r"^(?P<file>.*?):(?P<line>\d+):(?P<function>.*)$")
_FUNCTION_FILE_LINE = re.compile(
    r"^(?P<function>.*?)\s+\((?P<file>.*?):(?P<line>\d+)\)$"
)
_EMPTY_STACK_FRAME = "[no Python frames]"


@dataclass(frozen=True)
class CollapsedStack:
    frames: tuple[str, ...]
    samples: int


@dataclass
class FlameNode:
    frame: str
    samples: int = 0
    children: OrderedDict[str, FlameNode] = field(default_factory=OrderedDict)


def parse_collapsed_stacks(lines: Iterable[str]) -> list[CollapsedStack]:
    stacks: list[CollapsedStack] = []
    for line_number, line in enumerate(lines, start=1):
        text = line.strip()
        if not text:
            continue
        match = _COLLAPSED_LINE.fullmatch(text)
        if match is None:
            if text.isdecimal() and int(text) > 0:
                stacks.append(
                    CollapsedStack(
                        frames=(_EMPTY_STACK_FRAME,),
                        samples=int(text),
                    )
                )
                continue
            raise ValueError(f"Invalid collapsed stack at line {line_number}: {text!r}")
        frames = tuple(match.group("stack").split(";"))
        samples = int(match.group("count"))
        if not frames or any(not frame for frame in frames) or samples <= 0:
            raise ValueError(f"Invalid collapsed stack at line {line_number}: {text!r}")
        stacks.append(CollapsedStack(frames=frames, samples=samples))
    if not stacks:
        raise ValueError("The py-spy capture did not contain any samples")
    return stacks


def _frame_parts(frame: str) -> tuple[str, str, str]:
    match = _FILE_LINE_FUNCTION.fullmatch(frame)
    if match is not None:
        return match.group("file"), match.group("line"), match.group("function")
    match = _FUNCTION_FILE_LINE.fullmatch(frame)
    if match is not None:
        return match.group("file"), match.group("line"), match.group("function")
    return "", "", frame


def _frame_identity(frame: str) -> tuple[str, str]:
    filename, _, function = _frame_parts(frame)
    return filename, function


def _write_functions_csv(
    rows: list[dict[str, Any]],
    output_path: Path,
) -> None:
    fieldnames = [
        "file",
        "line",
        "function",
        "self_time_s",
        "total_time_s",
        "self_pct",
        "total_pct",
        "calls",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_sampled_artifacts(
    collapsed_path: Path,
    output_dir: Path,
    *,
    sample_rate: int,
) -> Path:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    with collapsed_path.open("r", encoding="utf-8") as handle:
        stacks = parse_collapsed_stacks(handle)

    interval = 1.0 / sample_rate
    total_samples = sum(stack.samples for stack in stacks)
    total_time = total_samples * interval
    frame_indices: dict[str, int] = {}
    frames: list[dict[str, Any]] = []
    samples: list[list[int]] = []
    weights: list[float] = []
    function_times: dict[str, dict[str, Any]] = {}
    root = FlameNode(frame="")

    for stack in stacks:
        frame_ids: list[int] = []
        for frame in stack.frames:
            frame_index = frame_indices.get(frame)
            if frame_index is None:
                filename, line, function = _frame_parts(frame)
                frame_index = len(frames)
                frame_indices[frame] = frame_index
                frame_data: dict[str, Any] = {"name": function}
                if filename:
                    frame_data["file"] = filename
                if line:
                    frame_data["line"] = int(line)
                frames.append(frame_data)
            frame_ids.append(frame_index)

        for _ in range(stack.samples):
            samples.append(frame_ids)
            weights.append(interval)

        leaf = stack.frames[-1]
        leaf_filename, leaf_line, leaf_function = _frame_parts(leaf)
        leaf_row = function_times.setdefault(
            leaf,
            {
                "file": leaf_filename,
                "line": leaf_line,
                "function": leaf_function,
                "self_time_s": 0.0,
                "total_time_s": 0.0,
                "calls": "",
            },
        )
        leaf_row["self_time_s"] += stack.samples * interval

        seen_functions: set[tuple[str, str]] = set()
        for frame in stack.frames:
            identity = _frame_identity(frame)
            if identity in seen_functions:
                continue
            seen_functions.add(identity)
            filename, line, function = _frame_parts(frame)
            row = function_times.setdefault(
                frame,
                {
                    "file": filename,
                    "line": line,
                    "function": function,
                    "self_time_s": 0.0,
                    "total_time_s": 0.0,
                    "calls": "",
                },
            )
            row["total_time_s"] += stack.samples * interval

        node = root
        node.samples += stack.samples
        for frame in stack.frames:
            node = node.children.setdefault(frame, FlameNode(frame=frame))
            node.samples += stack.samples

    _write_speedscope(output_dir / "speedscope.json", frames, samples, weights)
    _write_flamegraph(output_dir / "flamegraph.svg", root)

    rows = list(function_times.values())
    for row in rows:
        row["self_pct"] = row["self_time_s"] / total_time * 100 if total_time else 0.0
        row["total_pct"] = row["total_time_s"] / total_time * 100 if total_time else 0.0
    rows.sort(key=lambda row: (-row["self_time_s"], row["file"], row["function"]))
    functions_path = output_dir / "functions.csv"
    _write_functions_csv(rows, functions_path)
    return functions_path


def _write_speedscope(
    output_path: Path,
    frames: list[dict[str, Any]],
    samples: list[list[int]],
    weights: list[float],
) -> None:
    payload = {
        "$schema": "https://www.speedscope.app/file-format-schema.json",
        "shared": {"frames": frames},
        "profiles": [
            {
                "type": "sampled",
                "name": "py-spy",
                "unit": "seconds",
                "startValue": 0,
                "endValue": sum(weights),
                "samples": samples,
                "weights": weights,
            }
        ],
        "activeProfileIndex": 0,
        "exporter": "parcelpilot profiling",
    }
    output_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def _write_flamegraph(output_path: Path, root: FlameNode) -> None:
    width = 1200
    frame_height = 18
    max_depth = 0
    pending = [(root, 0)]
    while pending:
        node, depth = pending.pop()
        max_depth = max(max_depth, depth)
        pending.extend((child, depth + 1) for child in node.children.values())

    height = max(1, max_depth) * frame_height + 36
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#fff"/>',
        '<text x="8" y="16" font-family="sans-serif" font-size="12">py-spy sampled stacks</text>',
    ]
    work = [(root, 0.0, float(width), 0)]
    while work:
        parent, x, span, depth = work.pop()
        child_x = x
        children = list(parent.children.values())
        for child in children:
            child_span = span * child.samples / parent.samples if parent.samples else 0.0
            if child_span <= 0.25:
                child_x += child_span
                continue
            y = 24 + depth * frame_height
            color = "#e76f51" if depth % 2 == 0 else "#f4a261"
            title = escape(f"{child.frame} ({child.samples} samples)")
            elements.append(
                f'<g><title>{title}</title><rect x="{child_x:.3f}" y="{y}" '
                f'width="{max(0.0, child_span - 0.5):.3f}" height="{frame_height - 1}" '
                f'fill="{color}" stroke="#fff" stroke-width="0.5"/>'
            )
            if child_span >= 28:
                label = escape(child.frame)
                elements.append(
                    f'<text x="{child_x + 3:.3f}" y="{y + 13}" font-family="sans-serif" '
                    f'font-size="10" textLength="{max(1.0, child_span - 6):.3f}" '
                    f'lengthAdjust="spacingAndGlyphs">{label}</text>'
                )
            elements.append("</g>")
            work.append((child, child_x, child_span, depth + 1))
            child_x += child_span
    elements.append("</svg>")
    output_path.write_text("\n".join(elements), encoding="utf-8")


def write_cprofile_artifacts(profile_path: Path, output_path: Path) -> Path:
    stats = cProfile.Stats(str(profile_path))
    total_self_time = sum(values[2] for values in stats.stats.values())
    rows: list[dict[str, Any]] = []
    for (filename, line, function), values in stats.stats.items():
        _, calls, self_time, cumulative_time, _ = values
        rows.append(
            {
                "file": filename,
                "line": line,
                "function": function,
                "self_time_s": self_time,
                "total_time_s": cumulative_time,
                "self_pct": self_time / total_self_time * 100 if total_self_time else 0.0,
                "total_pct": cumulative_time / total_self_time * 100 if total_self_time else 0.0,
                "calls": calls,
            }
        )
    rows.sort(key=lambda row: (-row["self_time_s"], row["file"], row["line"], row["function"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_functions_csv(rows, output_path)
    return output_path


def capture_pyspy(
    pid: int,
    duration: float,
    output_dir: Path,
    *,
    sample_rate: int = 100,
) -> Path:
    executable = shutil.which("py-spy")
    if executable is None:
        raise RuntimeError(
            "py-spy is required for profiler=pyspy; install the pinned project dependency"
        )
    if duration <= 0:
        raise ValueError("duration must be positive")
    duration_seconds = int(duration)
    if duration_seconds != duration:
        raise ValueError("py-spy duration must be a whole number of seconds")
    output_dir.mkdir(parents=True, exist_ok=True)
    collapsed_path = output_dir / "stacks.collapsed"
    command = [
        executable,
        "record",
        "--pid",
        str(pid),
        "--duration",
        str(duration_seconds),
        "--rate",
        str(sample_rate),
        "--format",
        "raw",
        "--output",
        str(collapsed_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise RuntimeError(
            "py-spy could not attach to the API process. Check ptrace permissions "
            f"and the process ID. Details: {detail}"
        )
    if not collapsed_path.exists() or collapsed_path.stat().st_size == 0:
        raise RuntimeError("py-spy completed without writing stacks.collapsed")
    return write_sampled_artifacts(collapsed_path, output_dir, sample_rate=sample_rate)
