from __future__ import annotations

import json
from typing import Any

from spec_eval.runner import Report

_MARK = {"pass": "ok  ", "fail": "FAIL", "skip": "skip", "error": "ERR "}


def render_text(report: Report, verbose: bool = False) -> str:
    """Human-readable summary. Failing cases are always listed in full."""
    lines = [f"spec: {report.spec}", ""]
    for case in report.cases:
        lines.append(f"{'PASS' if case.passed else 'FAIL'}  {case.case}")
        for r in case.results:
            if verbose or r.status in ("fail", "error"):
                detail = f"  {r.detail}" if r.detail else ""
                lines.append(f"      {_MARK[r.status]} {r.criterion}{detail}")
    lines.append("")
    total = len(report.cases)
    lines.append(
        f"{report.passed_cases}/{total} cases passed ({report.rate:.0%}), "
        f"required {report.pass_rate:.0%}"
    )
    skipped, errors = report.count("skip"), report.count("error")
    if skipped:
        lines.append(f"{skipped} judge criteria skipped (no judge configured)")
    if errors:
        lines.append(f"{errors} criteria could not be graded")
    lines.append("result: " + ("PASS" if report.ok else "FAIL"))
    return "\n".join(lines)


def to_dict(report: Report) -> dict[str, Any]:
    return {
        "spec": report.spec,
        "ok": report.ok,
        "pass_rate": report.pass_rate,
        "rate": report.rate,
        "passed_cases": report.passed_cases,
        "total_cases": len(report.cases),
        "cases": [
            {
                "id": case.case,
                "passed": case.passed,
                "criteria": [
                    {"id": r.criterion, "status": r.status, "detail": r.detail}
                    for r in case.results
                ],
            }
            for case in report.cases
        ],
    }


def render_json(report: Report) -> str:
    return json.dumps(to_dict(report), indent=2, ensure_ascii=False)
