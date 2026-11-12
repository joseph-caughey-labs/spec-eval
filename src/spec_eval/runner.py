from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from spec_eval.checks import run_check
from spec_eval.judge import Judge, JudgeError
from spec_eval.spec import Case, Spec

Status = Literal["pass", "fail", "skip", "error"]


@dataclass(frozen=True)
class CriterionResult:
    criterion: str
    status: Status
    detail: str = ""


@dataclass(frozen=True)
class CaseResult:
    case: str
    results: tuple[CriterionResult, ...]

    @property
    def passed(self) -> bool:
        # A skipped criterion was not graded, so it can't fail a case. An error
        # means we don't know, and unknown is never a pass.
        return all(r.status in ("pass", "skip") for r in self.results)


@dataclass(frozen=True)
class Report:
    spec: str
    pass_rate: float
    cases: tuple[CaseResult, ...]

    @property
    def passed_cases(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def rate(self) -> float:
        return self.passed_cases / len(self.cases) if self.cases else 0.0

    @property
    def ok(self) -> bool:
        return bool(self.cases) and self.rate >= self.pass_rate

    def count(self, status: Status) -> int:
        return sum(1 for c in self.cases for r in c.results if r.status == status)


def evaluate(spec: Spec, cases: Sequence[Case], judge: Judge | None = None) -> Report:
    """Grade every case against every criterion.

    Without a judge, judge criteria are reported as skipped rather than passed,
    so a run that never consulted a model can't be mistaken for one that did.
    """
    results: list[CaseResult] = []
    for case in cases:
        graded: list[CriterionResult] = []
        for criterion in spec.criteria:
            if criterion.kind != "judge":
                check = run_check(criterion, case)
                status: Status = "pass" if check.passed else "fail"
                graded.append(CriterionResult(criterion.id, status, check.detail))
                continue
            if judge is None:
                graded.append(CriterionResult(criterion.id, "skip", "no judge configured"))
                continue
            try:
                verdict = judge.grade(criterion.params["rubric"], case)
            except JudgeError as exc:
                graded.append(CriterionResult(criterion.id, "error", str(exc)))
                continue
            status = "pass" if verdict.passed else "fail"
            graded.append(CriterionResult(criterion.id, status, verdict.reason))
        results.append(CaseResult(case.id, tuple(graded)))
    return Report(spec=spec.name, pass_rate=spec.pass_rate, cases=tuple(results))
