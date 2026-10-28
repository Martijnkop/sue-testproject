from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

RESULTS_ROOT = Path(__file__).resolve().parent / "results"


def ensure_results_dir() -> Path:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    return RESULTS_ROOT


def _manifest_path() -> Path:
    return Path(__file__).resolve().parents[2] / "ground_truth" / "issues.yaml"


def load_benchmark_threshold(issue_id: str) -> float | None:
    manifest_path = _manifest_path()
    if not manifest_path.exists():
        return None

    with manifest_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    items: list[dict[str, Any]] | None = raw.get("issues") if isinstance(raw, dict) else None
    if not items:
        items = raw if isinstance(raw, list) else []

    for item in items:
        if isinstance(item, dict) and item.get("id") == issue_id:
            return item.get("benchmark_threshold")
    return None


def record_benchmark_result(
    issue_id: str,
    *,
    median_ms: float,
    samples_ms: list[float] | None = None,
    threshold: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    ensure_results_dir()
    payload: dict[str, Any] = {
        "issue_id": issue_id,
        "median_ms": median_ms,
        "samples_ms": samples_ms or [median_ms],
        "threshold": threshold,
        "metadata": metadata or {},
    }
    path = RESULTS_ROOT / f"{issue_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
