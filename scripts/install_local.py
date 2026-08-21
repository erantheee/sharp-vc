#!/usr/bin/env python3
"""Install this checked-out Sharp VC source into a Codex skills directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1]
MANIFEST = (
    Path("SKILL.md"),
    Path("agents/openai.yaml"),
    Path("references/review-protocol.md"),
    Path("references/research-and-evidence.md"),
    Path("references/audit-template.md"),
    Path("references/eval-rubric.md"),
    Path("references/case-retrieval.md"),
    Path("references/investment-cases.jsonl"),
    Path("scripts/run_behavioral_evals.py"),
    Path("scripts/retrieve_investment_cases.py"),
    Path("scripts/validate_investment_cases.py"),
    Path("scripts/install_local.py"),
    Path("tests/cases.jsonl"),
    Path("tests/test_eval_runner.py"),
)


def install(target: Path) -> list[Path]:
    target = target.expanduser().resolve()
    if target.name != "sharp-vc":
        raise ValueError("target directory must be named sharp-vc")
    copied: list[Path] = []
    for relative in MANIFEST:
        source = SOURCE / relative
        if not source.is_file():
            raise FileNotFoundError(f"missing source file: {relative}")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(destination)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        type=Path,
        default=Path.home() / ".codex" / "skills" / "sharp-vc",
        help="existing or new sharp-vc installation directory",
    )
    args = parser.parse_args()
    try:
        copied = install(args.target)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"installed {len(copied)} files to {args.target.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
