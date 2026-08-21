import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_behavioral_evals import (
    EvalError,
    grade_response,
    read_jsonl,
    response_map,
    validate_cases,
)
from scripts.install_local import MANIFEST, install


ROOT = Path(__file__).resolve().parents[1]


class EvalRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = read_jsonl(ROOT / "tests" / "cases.jsonl")

    def test_suite_is_valid_and_bounded(self):
        self.assertEqual([], validate_cases(self.cases))
        self.assertGreaterEqual(len(self.cases), 20)
        self.assertLessEqual(len(self.cases), 30)

    def test_hard_grader_accepts_natural_single_question(self):
        case = next(row for row in self.cases if row["id"] == "natural-output-no-codes")
        response = "现在不能立项，因为缺少能支持这笔投入的付款证据。什么实际付款行为会让负责人改判？"
        self.assertEqual([], grade_response(case, response))

    def test_hard_grader_rejects_codes_labels_and_question_lists(self):
        case = next(row for row in self.cases if row["id"] == "natural-output-no-codes")
        response = "一句话结论：[判定：待证据] E2。为什么买？谁会买？"
        messages = [finding.message for finding in grade_response(case, response)]
        self.assertTrue(any("asked 2 questions" in message for message in messages))
        self.assertTrue(any("internal evidence code" in message for message in messages))
        self.assertTrue(any("internal verdict label" in message for message in messages))
        self.assertTrue(any("banned template opening" in message for message in messages))

    def test_summary_case_rejects_any_question(self):
        case = next(row for row in self.cases if row["id"] == "summary-audit")
        findings = grade_response(case, "核心命题已记录。下一项最小验证是什么？")
        self.assertTrue(any("maximum is 0" in finding.message for finding in findings))

    def test_duplicate_response_ids_fail(self):
        with self.assertRaises(EvalError):
            response_map([{"id": "x", "response": "a"}, {"id": "x", "response": "b"}])

    def test_invalid_jsonl_reports_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.jsonl"
            path.write_text('{"id": 1}\nnot-json\n', encoding="utf-8")
            with self.assertRaisesRegex(EvalError, r":2: invalid JSON"):
                read_jsonl(path)

    def test_advisory_rubric_is_present_for_every_case(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertTrue(case["expected"]["judge_rubric"])
                self.assertTrue(case["human_gold"])

    def test_every_case_has_explicit_question_limit(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertIn("max_questions", case["expected"]["hard"])

    def test_installer_copies_only_manifest_to_named_target(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "sharp-vc"
            copied = install(target)
            self.assertEqual(len(MANIFEST), len(copied))
            for relative in MANIFEST:
                self.assertEqual(
                    (ROOT / relative).read_bytes(),
                    (target / relative).read_bytes(),
                )


if __name__ == "__main__":
    unittest.main()
