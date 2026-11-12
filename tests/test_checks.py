from __future__ import annotations

from typing import Any

import pytest

from spec_eval.checks import run_check
from spec_eval.spec import Case, Criterion


def check(kind: str, output: str, inp: dict[str, Any] | None = None, **params: Any) -> bool:
    criterion = Criterion(id="c", kind=kind, params=params)
    return run_check(criterion, Case(id="x", output=output, input=inp or {})).passed


@pytest.mark.parametrize(
    ("kind", "output", "params", "expected"),
    [
        ("contains", "Order 42 shipped", {"value": "shipped"}, True),
        ("contains", "Order 42 SHIPPED", {"value": "shipped"}, False),
        ("contains", "Order 42 SHIPPED", {"value": "shipped", "ignore_case": True}, True),
        ("not_contains", "all good", {"value": "sorry"}, True),
        ("not_contains", "so sorry", {"value": "sorry"}, False),
        ("regex", "ref ABC-123", {"pattern": r"[A-Z]{3}-\d+"}, True),
        ("regex", "ref abc", {"pattern": r"[A-Z]{3}-\d+"}, False),
        ("not_regex", "call us", {"pattern": r"(?i)guarantee"}, True),
        ("not_regex", "We GUARANTEE it", {"pattern": r"(?i)guarantee"}, False),
        ("min_chars", "abcd", {"value": 4}, True),
        ("min_chars", "abc", {"value": 4}, False),
        ("max_chars", "abc", {"value": 3}, True),
        ("max_chars", "abcd", {"value": 3}, False),
        ("json", '{"a": 1}', {}, True),
        ("json", "{a: 1}", {}, False),
        ("json", '{"a": 1, "b": 2}', {"required_keys": ["a", "b"]}, True),
        ("json", '{"a": 1}', {"required_keys": ["a", "b"]}, False),
        ("json", "[1, 2]", {"required_keys": ["a"]}, False),
    ],
)
def test_checks(kind: str, output: str, params: dict[str, Any], expected: bool) -> None:
    assert check(kind, output, **params) is expected


def test_echoes_input() -> None:
    assert check("echoes_input", "Order 1042 is on its way", {"order": 1042}, field="order")
    assert not check("echoes_input", "Your order is on its way", {"order": 1042}, field="order")
    assert not check("echoes_input", "Order 1042", {}, field="order")


def test_failure_detail_explains_why() -> None:
    criterion = Criterion(id="c", kind="max_chars", params={"value": 2})
    result = run_check(criterion, Case(id="x", output="abcd"))
    assert result.detail == "4 chars, maximum 2"
