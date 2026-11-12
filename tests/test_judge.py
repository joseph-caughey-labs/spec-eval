from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from spec_eval.judge import (
    FALLBACK_BETA,
    VERDICT_SCHEMA,
    AnthropicJudge,
    CachedJudge,
    JudgeError,
    Verdict,
    build_prompt,
    parse_verdict,
)
from spec_eval.spec import Case

CASE = Case(id="c1", output="Thanks for waiting.", input={"order": 7})


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


def fake_client(text: str | None, stop_reason: str = "end_turn") -> tuple[Any, FakeMessages]:
    blocks = [] if text is None else [SimpleNamespace(type="text", text=text)]
    messages = FakeMessages(SimpleNamespace(stop_reason=stop_reason, content=blocks))
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


class CountingJudge:
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def grade(self, rubric: str, case: Case) -> Verdict:
        self.calls += 1
        return Verdict(passed=True, reason=f"graded {case.id}")


def test_prompt_wraps_output_and_input_as_data() -> None:
    prompt = build_prompt("  Be polite.  ", CASE)
    assert "<criterion>\nBe polite.\n</criterion>" in prompt
    assert '"order": 7' in prompt
    assert prompt.endswith("<output>\nThanks for waiting.\n</output>")


def test_prompt_omits_empty_input() -> None:
    assert "<input>" not in build_prompt("x", Case(id="c", output="y"))


def test_parse_verdict() -> None:
    assert parse_verdict('{"reason": "ok", "pass": true}') == Verdict(True, "ok")
    with pytest.raises(JudgeError, match="unreadable"):
        parse_verdict('{"reason": "no verdict"}')


def test_anthropic_judge_request_shape() -> None:
    client, messages = fake_client('{"reason": "Polite throughout.", "pass": true}')
    judge = AnthropicJudge(client=cast(Any, client), effort="low")

    assert judge.grade("Be polite.", CASE) == Verdict(True, "Polite throughout.")
    (call,) = messages.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
    }
    assert call["betas"] == [FALLBACK_BETA]
    assert call["fallbacks"] == "default"
    assert "<output>" in call["messages"][0]["content"]
    assert judge.name == "anthropic:claude-opus-5-5:low"


@pytest.mark.parametrize(
    ("text", "stop_reason", "message"),
    [
        (None, "refusal", "declined"),
        ('{"reason": "trunc', "max_tokens", "cut off"),
        (None, "end_turn", "no verdict"),
    ],
)
def test_anthropic_judge_errors(text: str | None, stop_reason: str, message: str) -> None:
    client, _ = fake_client(text, stop_reason)
    with pytest.raises(JudgeError, match=message):
        AnthropicJudge(client=cast(Any, client)).grade("x", CASE)


def test_cache_reuses_verdicts_across_runs(tmp_path: Path) -> None:
    path = tmp_path / "verdicts.json"
    inner = CountingJudge()

    first = CachedJudge(inner, path)
    first.grade("Be polite.", CASE)
    first.grade("Be polite.", CASE)
    first.save()
    assert (inner.calls, first.hits, first.misses) == (1, 1, 1)

    second = CachedJudge(inner, path, offline=True)
    assert second.grade("Be polite.", CASE) == Verdict(True, "graded c1")
    assert inner.calls == 1


def test_cache_key_changes_with_output_rubric_and_judge(tmp_path: Path) -> None:
    cache = CachedJudge(CountingJudge(), tmp_path / "v.json")
    base = cache.key("rubric", CASE)
    assert cache.key("other rubric", CASE) != base
    assert cache.key("rubric", Case(id="c1", output="changed", input={"order": 7})) != base
    assert cache.key("rubric", Case(id="renamed", output=CASE.output, input=CASE.input)) == base

    other = CountingJudge()
    other.name = "different-model"
    assert CachedJudge(other, tmp_path / "v.json").key("rubric", CASE) != base


def test_offline_cache_miss_is_an_error(tmp_path: Path) -> None:
    cache = CachedJudge(CountingJudge(), tmp_path / "missing.json", offline=True)
    with pytest.raises(JudgeError, match="offline"):
        cache.grade("x", CASE)


def test_save_skips_write_when_nothing_new(tmp_path: Path) -> None:
    path = tmp_path / "v.json"
    CachedJudge(CountingJudge(), path).save()
    assert not path.exists()


def test_corrupt_cache_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "v.json"
    path.write_text("{not json")
    with pytest.raises(JudgeError, match="not valid JSON"):
        CachedJudge(CountingJudge(), path)


def test_cache_file_is_stable_json(tmp_path: Path) -> None:
    path = tmp_path / "v.json"
    cache = CachedJudge(CountingJudge(), path)
    cache.grade("x", CASE)
    cache.save()
    (entry,) = json.loads(path.read_text()).values()
    assert entry == {"pass": True, "reason": "graded c1"}
