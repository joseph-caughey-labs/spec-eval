"""Deterministic checks. Each one is a pure function of the criterion and the case."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from spec_eval.spec import Case, Criterion


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    detail: str = ""


Check = Callable[[Criterion, Case], CheckResult]


def _contains(c: Criterion, case: Case) -> CheckResult:
    needle, hay = c.params["value"], case.output
    if c.params.get("ignore_case", False):
        needle, hay = needle.casefold(), hay.casefold()
    found = needle in hay
    return CheckResult(found, "" if found else f"missing {c.params['value']!r}")


def _not_contains(c: Criterion, case: Case) -> CheckResult:
    if _contains(c, case).passed:
        return CheckResult(False, f"contains {c.params['value']!r}")
    return CheckResult(True)


def _regex(c: Criterion, case: Case) -> CheckResult:
    found = re.search(c.params["pattern"], case.output) is not None
    return CheckResult(found, "" if found else f"no match for /{c.params['pattern']}/")


def _not_regex(c: Criterion, case: Case) -> CheckResult:
    match = re.search(c.params["pattern"], case.output)
    if match is None:
        return CheckResult(True)
    return CheckResult(False, f"matched {match.group(0)!r}")


def _min_chars(c: Criterion, case: Case) -> CheckResult:
    n, limit = len(case.output), c.params["value"]
    return CheckResult(n >= limit, "" if n >= limit else f"{n} chars, minimum {limit}")


def _max_chars(c: Criterion, case: Case) -> CheckResult:
    n, limit = len(case.output), c.params["value"]
    return CheckResult(n <= limit, "" if n <= limit else f"{n} chars, maximum {limit}")


def _json(c: Criterion, case: Case) -> CheckResult:
    try:
        value = json.loads(case.output)
    except json.JSONDecodeError as exc:
        return CheckResult(False, f"not valid JSON: {exc.msg}")
    required = c.params.get("required_keys", [])
    if required and not isinstance(value, dict):
        return CheckResult(False, "expected a JSON object")
    missing = [k for k in required if k not in value]
    if missing:
        return CheckResult(False, "missing keys: " + ", ".join(missing))
    return CheckResult(True)


def _echoes_input(c: Criterion, case: Case) -> CheckResult:
    name = c.params["field"]
    if name not in case.input:
        return CheckResult(False, f"case has no input field '{name}'")
    expected = str(case.input[name])
    found = expected in case.output
    return CheckResult(found, "" if found else f"does not mention {expected!r}")


CHECKS: dict[str, Check] = {
    "contains": _contains,
    "not_contains": _not_contains,
    "regex": _regex,
    "not_regex": _not_regex,
    "min_chars": _min_chars,
    "max_chars": _max_chars,
    "json": _json,
    "echoes_input": _echoes_input,
}


def run_check(criterion: Criterion, case: Case) -> CheckResult:
    return CHECKS[criterion.kind](criterion, case)
