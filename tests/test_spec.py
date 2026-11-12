from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from spec_eval.spec import SpecError, load_cases, load_spec, parse_spec


def spec_with(*criteria: dict[str, Any], **top: Any) -> dict[str, Any]:
    return {"name": "t", "criteria": list(criteria), **top}


def test_parses_valid_spec() -> None:
    spec = parse_spec(
        spec_with(
            {"id": "short", "kind": "max_chars", "value": 10},
            {"id": "tone", "kind": "judge", "rubric": "Polite."},
            pass_rate=0.9,
        )
    )
    assert spec.name == "t"
    assert spec.pass_rate == 0.9
    assert [c.id for c in spec.criteria] == ["short", "tone"]
    assert spec.criteria[0].params == {"value": 10}


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"criteria": [{"id": "a", "kind": "json"}]}, "'name'"),
        (spec_with(), "at least one"),
        (spec_with({"id": "a", "kind": "nope"}), "unknown kind"),
        (spec_with({"id": "A B", "kind": "json"}), "'id'"),
        (spec_with({"id": "a", "kind": "contains"}), "missing 'value'"),
        (spec_with({"id": "a", "kind": "contains", "value": 3}), "'value' must be str"),
        (spec_with({"id": "a", "kind": "max_chars", "value": True}), "must be int"),
        (spec_with({"id": "a", "kind": "max_chars", "value": -1}), "not be negative"),
        (spec_with({"id": "a", "kind": "json", "extra": 1}), "unexpected key 'extra'"),
        (spec_with({"id": "a", "kind": "regex", "pattern": "("}), "invalid pattern"),
        (spec_with({"id": "a", "kind": "judge", "rubric": "  "}), "must not be empty"),
        (spec_with({"id": "a", "kind": "json", "required_keys": [1]}), "list of strings"),
        (spec_with({"id": "a", "kind": "json"}, {"id": "a", "kind": "json"}), "duplicate"),
        (spec_with({"id": "a", "kind": "json"}, pass_rate=1.5), "between 0 and 1"),
        (spec_with({"id": "a", "kind": "json"}, pass_rate=True), "must be a number"),
    ],
)
def test_rejects_invalid_spec(data: dict[str, Any], message: str) -> None:
    with pytest.raises(SpecError, match=message):
        parse_spec(data)


def test_load_spec_reports_toml_errors(tmp_path: Path) -> None:
    path = tmp_path / "spec.toml"
    path.write_text("name = ")
    with pytest.raises(SpecError, match="invalid TOML"):
        load_spec(path)


def test_load_cases(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        '{"id": "1", "output": "hi", "input": {"name": "Ana"}}\n\n{"id": "2", "output": ""}\n'
    )
    cases = load_cases(path)
    assert [c.id for c in cases] == ["1", "2"]
    assert cases[0].input == {"name": "Ana"}
    assert cases[1].input == {}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not json\n", ":1: invalid JSON"),
        ("[1]\n", "JSON object"),
        ('{"output": "x"}\n', "'id'"),
        ('{"id": "1", "output": 2}\n', "'output'"),
        ('{"id": "1", "output": "x", "input": []}\n', "'input'"),
        ('{"id": "1", "output": "x"}\n{"id": "1", "output": "y"}\n', ":2: duplicate"),
        ("\n", "no cases"),
    ],
)
def test_load_cases_rejects_bad_rows(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(content)
    with pytest.raises(SpecError, match=message):
        load_cases(path)
