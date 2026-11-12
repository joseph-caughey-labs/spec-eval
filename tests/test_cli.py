from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_eval.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main
from spec_eval.judge import DEFAULT_MODEL, CachedJudge, Verdict, anthropic_judge_name
from spec_eval.runner import evaluate
from spec_eval.spec import Case, load_cases, load_spec

EXAMPLE = Path(__file__).parent.parent / "examples" / "support-replies"
SPEC, CASES = str(EXAMPLE / "spec.toml"), str(EXAMPLE / "cases.jsonl")


def test_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", SPEC]) == EXIT_OK
    assert "6 criteria (2 judged) OK" in capsys.readouterr().out


def test_run_example_reports_known_failures(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["run", SPEC, CASES, "--format", "json"]) == EXIT_FAILED
    data = json.loads(capsys.readouterr().out)
    passed = {c["id"]: c["passed"] for c in data["cases"]}
    assert passed == {
        "on-time-update": True,
        "promises-refund": False,
        "missing-order-id": False,
        "internal-link": False,
    }


def test_run_passes_when_rate_is_met(tmp_path: Path) -> None:
    spec = tmp_path / "spec.toml"
    spec.write_text('name = "s"\n[[criteria]]\nid = "a"\nkind = "contains"\nvalue = "ok"\n')
    cases = tmp_path / "cases.jsonl"
    cases.write_text('{"id": "1", "output": "ok"}\n')
    assert main(["run", str(spec), str(cases)]) == EXIT_OK


class AlwaysPass:
    """Pretends to be the default Anthropic judge so its verdicts land under that name."""

    name = anthropic_judge_name(DEFAULT_MODEL, "medium")

    def grade(self, rubric: str, case: Case) -> Verdict:
        return Verdict(True, "seeded")


def test_offline_run_replays_cached_verdicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache_path = tmp_path / "verdicts.json"
    seed = CachedJudge(AlwaysPass(), cache_path)
    evaluate(load_spec(SPEC), load_cases(CASES), seed)
    seed.save()

    code = main(
        ["run", SPEC, CASES, "--judge", "anthropic", "--cache", str(cache_path), "--offline"]
    )
    out = capsys.readouterr().out
    assert code == EXIT_FAILED  # the deterministic failures still fail
    assert "judge cache: 8 reused, 0 new" in out
    assert "skipped" not in out
    assert "could not be graded" not in out


def test_offline_miss_is_an_error_not_an_api_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "empty.json"
    code = main(["run", SPEC, CASES, "--judge", "anthropic", "--cache", str(cache), "--offline"])
    assert code == EXIT_FAILED
    assert "running offline" in capsys.readouterr().out


@pytest.mark.parametrize(
    "args",
    [
        ["run", SPEC, CASES, "--offline"],
        ["run", SPEC, CASES, "--offline", "--cache", "x.json"],
        ["run", SPEC, "missing.jsonl"],
        ["check", "missing.toml"],
    ],
)
def test_usage_errors(args: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(args) == EXIT_USAGE
    assert capsys.readouterr().err.startswith("spec-eval: ")
