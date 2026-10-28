from __future__ import annotations

import re
from pathlib import Path

import yaml

BANNED_PATTERNS = (
    re.compile(r"(?i)\bslow\b"),
    re.compile(r"(?i)\bnaive\b"),
    re.compile(r"(?i)\bbad\b"),
    re.compile(r"(?i)\binefficient\b"),
    re.compile(r"(?i)TODO\s+optimize"),
    re.compile(r"(?i)(?:H(?:10|[1-9])|P(?:1[0-4]|[1-9]))\b"),
)


def _iter_python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if "site-packages" in str(path):
            continue
        rel = path.relative_to(root)
        if rel.parts[:1] == ("ground_truth",) or rel.parts[:1] == ("tests",):
            continue
        yield path


def _manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "ground_truth" / "issues.yaml"


def test_no_hints_in_parcelpilot_package() -> None:
    package_root = Path(__file__).resolve().parents[1]
    hits: list[str] = []

    for path in _iter_python_files(package_root):
        text = path.read_text(encoding="utf-8")
        for pattern in BANNED_PATTERNS:
            if pattern.search(text):
                hits.append(f"{path.relative_to(package_root)} matches {pattern.pattern}")

    assert not hits, "Banned hint words or issue IDs were found in parcelpilot/:\n" + "\n".join(hits)


def test_issue_manifest_schema() -> None:
    manifest_path = _manifest_path()
    assert manifest_path.exists(), f"Missing issue manifest: {manifest_path}"

    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle) or {}

    issues = manifest.get("issues")
    assert isinstance(issues, list) and issues, "Manifest must define a non-empty issues list"

    ids: list[str] = []
    allowed_fix_scopes = {"leaf", "caller", "architectural", "none"}

    for item in issues:
        assert isinstance(item, dict)
        required = {
            "id",
            "title",
            "endpoints",
            "planted_in",
            "visible_in",
            "profile_signature",
            "correct_fix_location",
            "fix_scope",
            "difficulty_detect",
            "difficulty_fix",
            "oracle",
            "benchmark_threshold",
        }
        assert required.issubset(item), f"Manifest item missing required keys: {item.get('id')}"
        assert item["id"] not in ids, f"Duplicate issue id: {item['id']}"
        ids.append(item["id"])
        assert item["fix_scope"] in allowed_fix_scopes
        assert isinstance(item["endpoints"], list) and item["endpoints"]
        assert isinstance(item["profile_signature"], list) and item["profile_signature"]
        assert isinstance(item["benchmark_threshold"], (int, float))

    assert ids == sorted(ids, key=lambda item: item.upper()), "Issue IDs should be ordered for readability"
