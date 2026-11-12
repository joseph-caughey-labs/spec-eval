from __future__ import annotations

from spec_eval.judge import JudgeError, Verdict
from spec_eval.report import render_text, to_dict
from spec_eval.runner import evaluate
from spec_eval.spec import Case, Criterion, Spec

SPEC = Spec(
    name="demo",
    criteria=(
        Criterion("short", "max_chars", {"value": 10}),
        Criterion("polite", "judge", {"rubric": "Polite."}),
    ),
    pass_rate=0.5,
)
CASES = [Case("good", "thanks!"), Case("long", "this reply is far too long")]


class ScriptedJudge:
    name = "scripted"

    def __init__(self, verdicts: dict[str, Verdict | Exception]) -> None:
        self.verdicts = verdicts

    def grade(self, rubric: str, case: Case) -> Verdict:
        result = self.verdicts[case.id]
        if isinstance(result, Exception):
            raise result
        return result


def test_without_judge_judge_criteria_are_skipped_not_passed() -> None:
    report = evaluate(SPEC, CASES)
    assert [c.passed for c in report.cases] == [True, False]
    assert report.count("skip") == 2
    assert report.ok  # 1 of 2 meets the 0.5 pass rate


def test_judge_verdicts_decide_cases() -> None:
    judge = ScriptedJudge({"good": Verdict(False, "curt"), "long": Verdict(True, "fine")})
    report = evaluate(SPEC, CASES, judge)
    assert report.passed_cases == 0
    assert not report.ok
    assert report.cases[0].results[1].detail == "curt"


def test_judge_error_fails_the_case() -> None:
    judge = ScriptedJudge({"good": JudgeError("boom"), "long": Verdict(True, "fine")})
    report = evaluate(SPEC, CASES, judge)
    assert report.cases[0].results[1].status == "error"
    assert not report.cases[0].passed
    assert "1 criteria could not be graded" in render_text(report)


def test_text_report_lists_failures_and_hides_passes_unless_verbose() -> None:
    report = evaluate(SPEC, CASES)
    text = render_text(report)
    assert "FAIL short  26 chars, maximum 10" in text
    assert "ok   short" not in text
    assert "ok   short" in render_text(report, verbose=True)
    assert text.endswith("result: PASS")


def test_dict_report() -> None:
    data = to_dict(evaluate(SPEC, CASES))
    assert data["ok"] is True
    assert (data["passed_cases"], data["total_cases"]) == (1, 2)
    assert data["cases"][1]["criteria"][0] == {
        "id": "short",
        "status": "fail",
        "detail": "26 chars, maximum 10",
    }


def test_empty_case_list_is_not_ok() -> None:
    assert not evaluate(SPEC, []).ok
