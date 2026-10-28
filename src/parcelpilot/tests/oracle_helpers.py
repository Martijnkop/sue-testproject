from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ORACLE_ROOT = Path(__file__).resolve().parent / "oracles"


def ensure_oracle_dir() -> Path:
    ORACLE_ROOT.mkdir(parents=True, exist_ok=True)
    return ORACLE_ROOT


def write_oracle(issue_id: str, payload: Any) -> Path:
    ensure_oracle_dir()
    path = ORACLE_ROOT / f"{issue_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_oracle(issue_id: str) -> Any:
    path = ORACLE_ROOT / f"{issue_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No oracle found for {issue_id!r} at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compare_exact(actual: Any, expected: Any) -> bool:
    return actual == expected


def compare_float_tolerance(actual: float, expected: float, *, atol: float = 1e-9) -> bool:
    return abs(actual - expected) <= atol


def compare_unordered(actual: list[Any] | tuple[Any, ...], expected: list[Any] | tuple[Any, ...]) -> bool:
    return sorted(actual, key=lambda item: json.dumps(item, sort_keys=True)) == sorted(
        expected, key=lambda item: json.dumps(item, sort_keys=True)
    )


def compare_set_equal(actual: set[Any], expected: set[Any]) -> bool:
    return actual == expected
