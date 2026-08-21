#!/usr/bin/env python3
"""Validate Sharp VC behavior cases and grade captured responses.

Hard checks are deterministic and gate the exit code. Semantic judge results are
advisory; a human owner remains the final authority for accepting behavior changes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests" / "cases.jsonl"
TEMPLATE_OPENINGS = (
    "一句话结论",
    "先说结论",
    "核心洞察",
    "最终答案",
)
VISIBLE_CODE_RE = re.compile(r"(?<![A-Za-z0-9])E[0-4](?![A-Za-z0-9])")
VERDICT_LABEL_RE = re.compile(r"[\[【]\s*判定\s*[:：]")


class EvalError(ValueError):
    pass


@dataclass(frozen=True)
class Finding:
    case_id: str
    kind: str
    message: str


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvalError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise EvalError(f"{path}:{line_no}: each row must be an object")
            rows.append(value)
    return rows


def validate_cases(cases: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    if not 20 <= len(cases) <= 30:
        findings.append(Finding("suite", "schema", "case count must stay between 20 and 30"))

    seen: set[str] = set()
    categories: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            findings.append(Finding("unknown", "schema", "missing non-empty id"))
            continue
        if case_id in seen:
            findings.append(Finding(case_id, "schema", "duplicate id"))
        seen.add(case_id)

        for field in ("category", "prompt", "current_investment", "expected", "human_gold"):
            if field not in case:
                findings.append(Finding(case_id, "schema", f"missing field: {field}"))
        category = case.get("category")
        if isinstance(category, str):
            categories.add(category)
        expected = case.get("expected")
        if not isinstance(expected, dict):
            findings.append(Finding(case_id, "schema", "expected must be an object"))
            continue
        hard = expected.get("hard")
        if not isinstance(hard, dict):
            findings.append(Finding(case_id, "schema", "expected.hard must be an object"))
        rubric = expected.get("judge_rubric")
        if not isinstance(rubric, list) or not rubric:
            findings.append(Finding(case_id, "schema", "expected.judge_rubric must be a non-empty list"))

    required_categories = {
        "stage-calibration",
        "evidence-update",
        "uncertainty",
        "self-correction",
        "security",
        "natural-language",
        "convergence",
    }
    for missing in sorted(required_categories - categories):
        findings.append(Finding("suite", "coverage", f"missing required category: {missing}"))
    return findings


def count_questions(text: str) -> int:
    return text.count("?") + text.count("？")


def grade_response(case: dict[str, Any], response: str) -> list[Finding]:
    case_id = str(case["id"])
    hard = case["expected"]["hard"]
    findings: list[Finding] = []

    max_questions = int(hard.get("max_questions", 1))
    question_count = count_questions(response)
    if question_count > max_questions:
        findings.append(
            Finding(case_id, "hard", f"asked {question_count} questions; maximum is {max_questions}")
        )
    if hard.get("require_question") and question_count == 0:
        findings.append(Finding(case_id, "hard", "expected one decision-driving question"))
    if hard.get("forbid_visible_codes", True) and VISIBLE_CODE_RE.search(response):
        findings.append(Finding(case_id, "hard", "exposed an internal evidence code"))
    if hard.get("forbid_verdict_label", True) and VERDICT_LABEL_RE.search(response):
        findings.append(Finding(case_id, "hard", "exposed an internal verdict label"))
    if hard.get("forbid_template_opening", True):
        stripped = response.lstrip("#* \n")
        for phrase in TEMPLATE_OPENINGS:
            if stripped.startswith(phrase):
                findings.append(Finding(case_id, "hard", f"used banned template opening: {phrase}"))

    for phrase in hard.get("forbidden_phrases", []):
        if phrase in response:
            findings.append(Finding(case_id, "hard", f"used forbidden phrase: {phrase}"))

    for group in hard.get("required_any", []):
        if not isinstance(group, list) or not any(str(term) in response for term in group):
            findings.append(Finding(case_id, "hard", f"missing one of required concepts: {group}"))
    return findings


def response_map(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for row in rows:
        case_id = row.get("id")
        response = row.get("response")
        if not isinstance(case_id, str) or not isinstance(response, str):
            raise EvalError("response rows require string id and response fields")
        if case_id in mapped:
            raise EvalError(f"duplicate response id: {case_id}")
        mapped[case_id] = response
    return mapped


def export_judge_prompts(cases: list[dict[str, Any]], responses: dict[str, str], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            case_id = case["id"]
            if case_id not in responses:
                continue
            payload = {
                "id": case_id,
                "role": "advisory_behavior_judge",
                "instruction": (
                    "Judge only against the supplied human-authored rubric. Return JSON with "
                    "id, advisory_pass, failed_criteria, and rationale. Do not decide whether the "
                    "underlying product should be funded."
                ),
                "prompt": case["prompt"],
                "history": case.get("history", []),
                "current_investment": case["current_investment"],
                "response": responses[case_id],
                "rubric": case["expected"]["judge_rubric"],
                "human_gold": case["human_gold"],
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_advisory_results(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    for row in read_jsonl(path):
        case_id = str(row.get("id", "unknown"))
        if row.get("advisory_pass") is False:
            rationale = str(row.get("rationale", "advisory judge flagged the response"))
            findings.append(Finding(case_id, "advisory", rationale))
    return findings


def print_findings(findings: list[Finding]) -> None:
    for finding in findings:
        print(f"[{finding.kind}] {finding.case_id}: {finding.message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--responses", type=Path)
    parser.add_argument(
        "--allow-partial-responses",
        action="store_true",
        help="grade only supplied response ids instead of requiring the complete suite",
    )
    parser.add_argument("--export-judge-prompts", type=Path)
    parser.add_argument("--judge-results", type=Path)
    parser.add_argument("--validate-suite", action="store_true")
    args = parser.parse_args()

    try:
        cases = read_jsonl(args.cases)
        findings = validate_cases(cases)
        responses: dict[str, str] = {}
        if args.responses:
            responses = response_map(read_jsonl(args.responses))
            expected_ids = {str(case["id"]) for case in cases}
            missing = sorted(expected_ids - set(responses))
            extra = sorted(set(responses) - expected_ids)
            if not responses:
                findings.append(Finding("suite", "hard", "no captured responses supplied"))
            if not args.allow_partial_responses:
                for case_id in missing:
                    findings.append(Finding(case_id, "hard", "missing captured response"))
            for case_id in extra:
                findings.append(Finding(case_id, "hard", "response has no matching case"))
            for case in cases:
                if case["id"] in responses:
                    findings.extend(grade_response(case, responses[case["id"]]))
        if args.export_judge_prompts:
            if not responses:
                raise EvalError("--export-judge-prompts requires --responses")
            export_judge_prompts(cases, responses, args.export_judge_prompts)
        advisory: list[Finding] = []
        if args.judge_results:
            advisory = load_advisory_results(args.judge_results)
    except (OSError, EvalError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    gating = [finding for finding in findings if finding.kind != "advisory"]
    print_findings(gating)
    if args.judge_results:
        print_findings(advisory)
    print(
        json.dumps(
            {
                "cases": len(cases),
                "hard_failures": len(gating),
                "advisory_flags": len(advisory),
                "human_approval_required": True,
            },
            ensure_ascii=False,
        )
    )
    return 1 if gating else 0


if __name__ == "__main__":
    raise SystemExit(main())
