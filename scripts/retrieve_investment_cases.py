#!/usr/bin/env python3
"""Retrieve structurally similar Sharp VC investment cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "references" / "investment-cases.jsonl"


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: case must be an object")
        cases.append(value)
    return cases


def terms(value: str) -> set[str]:
    return {part.strip().lower() for part in value.split(",") if part.strip()}


def rank_cases(
    cases: list[dict[str, Any]], tags: set[str], patterns: set[str], stage: str | None
) -> list[tuple[int, dict[str, Any]]]:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for case in cases:
        case_tags = {str(item).lower() for item in case.get("archetypes", [])}
        case_tags |= {str(item).lower() for item in case.get("sectors", [])}
        case_patterns = {str(item).lower() for item in case.get("patterns", [])}
        tag_matches = len(tags & case_tags)
        pattern_matches = len(patterns & case_patterns)
        score = 3 * tag_matches + 5 * pattern_matches
        if stage and stage.lower() == str(case.get("stage", "")).lower():
            score += 2
        structural_match = pattern_matches > 0 or tag_matches >= 2
        broad_tag_search = not patterns and not stage and tag_matches > 0
        stage_search = bool(stage) and not tags and not patterns and score > 0
        if structural_match or broad_tag_search or stage_search:
            ranked.append((score, case))
    return sorted(ranked, key=lambda item: (-item[0], str(item[1]["id"])))


def public_view(case: dict[str, Any], include_outcome: bool) -> dict[str, Any]:
    fields = (
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
        "anti_analogy",
        "sources",
    )
    value = {field: case[field] for field in fields}
    if include_outcome:
        value["later_outcome"] = case["later_outcome"]
        value["lesson"] = case["lesson"]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--tags", default="")
    parser.add_argument("--patterns", default="")
    parser.add_argument("--stage")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--include-outcome", action="store_true")
    parser.add_argument("--list-vocabulary", action="store_true")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    if args.list_vocabulary:
        vocabulary = {
            "tags": sorted(
                {
                    str(item)
                    for case in cases
                    for field in ("sectors", "archetypes")
                    for item in case[field]
                }
            ),
            "patterns": sorted({str(item) for case in cases for item in case["patterns"]}),
            "stages": sorted({str(case["stage"]) for case in cases}),
        }
        print(json.dumps(vocabulary, ensure_ascii=False, indent=2))
        return 0

    if args.limit < 1 or args.limit > 3:
        parser.error("--limit must be between 1 and 3")
    tags = terms(args.tags)
    patterns = terms(args.patterns)
    if not tags and not patterns and not args.stage:
        parser.error("provide --tags, --patterns, or --stage")
    ranked = rank_cases(cases, tags, patterns, args.stage)
    for score, case in ranked[: args.limit]:
        result = public_view(case, args.include_outcome)
        result["match_score"] = score
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
