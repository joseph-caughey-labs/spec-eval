"""Loading and validating specs and the cases graded against them."""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SpecError(ValueError):
    """Raised for a spec or cases file that can't be used as written."""


@dataclass(frozen=True)
class Criterion:
    id: str
    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Spec:
    name: str
    criteria: tuple[Criterion, ...]
    # Fraction of cases that must pass every criterion for the run to succeed.
    pass_rate: float = 1.0


@dataclass(frozen=True)
class Case:
    id: str
    output: str
    input: Mapping[str, Any] = field(default_factory=dict)


# kind -> (required params, optional params), each mapped to the accepted type.
PARAMS: dict[str, tuple[dict[str, type], dict[str, type]]] = {
    "contains": ({"value": str}, {"ignore_case": bool}),
    "not_contains": ({"value": str}, {"ignore_case": bool}),
    "regex": ({"pattern": str}, {}),
    "not_regex": ({"pattern": str}, {}),
    "min_chars": ({"value": int}, {}),
    "max_chars": ({"value": int}, {}),
    "json": ({}, {"required_keys": list}),
    "echoes_input": ({"field": str}, {}),
    "judge": ({"rubric": str}, {}),
}

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def load_spec(path: str | Path) -> Spec:
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SpecError(f"{path}: invalid TOML: {exc}") from exc
    return parse_spec(data, source=str(path))


def parse_spec(data: Mapping[str, Any], source: str = "spec") -> Spec:
    name = data.get("name")
    if not isinstance(name, str) or not name:
        raise SpecError(f"{source}: 'name' must be a non-empty string")

    pass_rate = data.get("pass_rate", 1.0)
    # bool is an int subclass; reject it so `pass_rate = true` isn't read as 1.0.
    if isinstance(pass_rate, bool) or not isinstance(pass_rate, int | float):
        raise SpecError(f"{source}: 'pass_rate' must be a number")
    if not 0.0 <= pass_rate <= 1.0:
        raise SpecError(f"{source}: 'pass_rate' must be between 0 and 1")

    raw = data.get("criteria")
    if not isinstance(raw, list) or not raw:
        raise SpecError(f"{source}: at least one [[criteria]] entry is required")

    criteria: list[Criterion] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw, start=1):
        where = f"{source}: criteria #{index}"
        if not isinstance(entry, dict):
            raise SpecError(f"{where}: must be a table")
        criterion = _parse_criterion(entry, where)
        if criterion.id in seen:
            raise SpecError(f"{where}: duplicate id '{criterion.id}'")
        seen.add(criterion.id)
        criteria.append(criterion)

    return Spec(name=name, criteria=tuple(criteria), pass_rate=float(pass_rate))


def _parse_criterion(entry: dict[str, Any], where: str) -> Criterion:
    params = dict(entry)
    cid = params.pop("id", None)
    kind = params.pop("kind", None)
    if not isinstance(cid, str) or not _ID.match(cid):
        raise SpecError(f"{where}: 'id' must be lowercase letters, digits, '-' or '_'")
    where = f"{where} ({cid})"
    if kind not in PARAMS:
        known = ", ".join(sorted(PARAMS))
        raise SpecError(f"{where}: unknown kind {kind!r}; expected one of {known}")

    required, optional = PARAMS[kind]
    for key in required:
        if key not in params:
            raise SpecError(f"{where}: missing '{key}'")
    for key, value in params.items():
        expected = required.get(key) or optional.get(key)
        if expected is None:
            raise SpecError(f"{where}: unexpected key '{key}' for kind '{kind}'")
        if isinstance(value, bool) and expected is not bool:
            raise SpecError(f"{where}: '{key}' must be {expected.__name__}")
        if not isinstance(value, expected):
            raise SpecError(f"{where}: '{key}' must be {expected.__name__}")

    if kind in ("regex", "not_regex"):
        try:
            re.compile(params["pattern"])
        except re.error as exc:
            raise SpecError(f"{where}: invalid pattern: {exc}") from exc
    if kind in ("min_chars", "max_chars") and params["value"] < 0:
        raise SpecError(f"{where}: 'value' must not be negative")
    if kind == "json" and not all(isinstance(k, str) for k in params.get("required_keys", [])):
        raise SpecError(f"{where}: 'required_keys' must be a list of strings")
    if kind == "judge" and not params["rubric"].strip():
        raise SpecError(f"{where}: 'rubric' must not be empty")

    return Criterion(id=cid, kind=kind, params=params)


def load_cases(path: str | Path) -> list[Case]:
    """Read cases from JSON Lines: one {"id", "output", "input"?} object per line."""
    cases: list[Case] = []
    seen: set[str] = set()
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        where = f"{path}:{lineno}"
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SpecError(f"{where}: invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise SpecError(f"{where}: each line must be a JSON object")
        cid, output, inp = row.get("id"), row.get("output"), row.get("input", {})
        if not isinstance(cid, str) or not cid:
            raise SpecError(f"{where}: 'id' must be a non-empty string")
        if not isinstance(output, str):
            raise SpecError(f"{where}: 'output' must be a string")
        if not isinstance(inp, dict):
            raise SpecError(f"{where}: 'input' must be an object")
        if cid in seen:
            raise SpecError(f"{where}: duplicate case id '{cid}'")
        seen.add(cid)
        cases.append(Case(id=cid, output=output, input=inp))
    if not cases:
        raise SpecError(f"{path}: no cases found")
    return cases
