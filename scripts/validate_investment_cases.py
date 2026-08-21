#!/usr/bin/env python3
"""Validate the source-backed Sharp VC investment case library."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "references" / "investment-cases.jsonl"
REQUIRED_FIELDS = {
    "id",
    "company",
    "decision_kind",
    "stage",
    "sectors",
    "archetypes",
    "patterns",
    "at_time_evidence",
    "decision",
    "rationale",
    "later_outcome",
    "lesson",
    "anti_analogy",
    "source_mode",
    "sources",
}


def validate(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: invalid JSON: {exc}")
            continue
        if not isinstance(row, dict):
            errors.append(f"line {line_no}: row must be an object")
            continue
        rows.append(row)
        missing = sorted(REQUIRED_FIELDS - row.keys())
        if missing:
            errors.append(f"line {line_no}: missing fields {missing}")
            continue
        case_id = row["id"]
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"line {line_no}: invalid id")
        elif case_id in seen:
            errors.append(f"line {line_no}: duplicate id {case_id}")
        seen.add(str(case_id))
        for field in ("sectors", "archetypes", "patterns", "at_time_evidence", "rationale", "sources"):
            if not isinstance(row[field], list) or not row[field]:
                errors.append(f"{case_id}: {field} must be a non-empty list")
        for field in ("company", "stage", "decision", "later_outcome", "lesson", "anti_analogy", "source_mode"):
            if not isinstance(row[field], str) or not row[field].strip():
                errors.append(f"{case_id}: {field} must be a non-empty string")
        for source in row["sources"] if isinstance(row["sources"], list) else []:
            if not isinstance(source, dict) or not str(source.get("url", "")).startswith("https://"):
                errors.append(f"{case_id}: source requires an https URL")
            if not isinstance(source, dict) or not str(source.get("title", "")).strip():
                errors.append(f"{case_id}: source requires a title")

    if not 20 <= len(rows) <= 30:
        errors.append("library must contain between 20 and 30 cases")
    kinds = Counter(str(row.get("decision_kind")) for row in rows)
    if kinds["invest"] < 5 or kinds["pass"] < 5:
        errors.append("library requires at least five invest and five pass cases")
    if kinds["stop"] + kinds["pivot"] < 3:
        errors.append("library requires at least three stop or pivot cases")
    hardware = sum("hardware" in row.get("archetypes", []) for row in rows)
    if hardware < 3:
        errors.append("library requires at least three hardware cases")
    return rows, errors


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CASES
    try:
        rows, errors = validate(path)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"ERROR: {error}")
    kinds = Counter(str(row.get("decision_kind")) for row in rows)
    print(json.dumps({"cases": len(rows), "decision_kinds": kinds, "errors": len(errors)}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
