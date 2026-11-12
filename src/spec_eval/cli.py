from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from spec_eval import __version__
from spec_eval.judge import (
    DEFAULT_MODEL,
    EFFORTS,
    AnthropicJudge,
    CachedJudge,
    Judge,
    JudgeError,
    OfflineJudge,
    anthropic_judge_name,
)
from spec_eval.report import render_json, render_text
from spec_eval.runner import evaluate
from spec_eval.spec import SpecError, load_cases, load_spec

# 0: run met its pass rate. 1: it didn't. 2: the run couldn't happen as asked.
EXIT_OK, EXIT_FAILED, EXIT_USAGE = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spec-eval",
        description="Grade LLM output against a written spec.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate a spec without grading anything")
    check.add_argument("spec")

    run = sub.add_parser("run", help="grade cases against a spec")
    run.add_argument("spec", help="TOML spec file")
    run.add_argument("cases", help="JSON Lines file of cases")
    run.add_argument(
        "--judge",
        choices=("none", "anthropic"),
        default="none",
        help="how to grade judge criteria (default: none, which skips them)",
    )
    run.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"judge model (default: {DEFAULT_MODEL})"
    )
    run.add_argument("--effort", choices=EFFORTS, default="medium", help="judge effort level")
    run.add_argument("--cache", help="verdict cache file; reused across runs")
    run.add_argument(
        "--offline",
        action="store_true",
        help="grade only from --cache; a missing verdict is an error, not an API call",
    )
    run.add_argument("--format", choices=("text", "json"), default="text")
    run.add_argument("-v", "--verbose", action="store_true", help="list passing criteria too")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "check":
            spec = load_spec(args.spec)
            judged = sum(1 for c in spec.criteria if c.kind == "judge")
            print(f"{spec.name}: {len(spec.criteria)} criteria ({judged} judged) OK")
            return EXIT_OK
        return _run(args)
    except (SpecError, JudgeError, OSError) as exc:
        print(f"spec-eval: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _run(args: argparse.Namespace) -> int:
    if args.offline and not args.cache:
        raise SpecError("--offline needs --cache")
    if args.offline and args.judge == "none":
        raise SpecError("--offline needs --judge to say which judge's verdicts to read")

    spec = load_spec(args.spec)
    cases = load_cases(args.cases)

    judge: Judge | None = None
    cache: CachedJudge | None = None
    if args.judge == "anthropic":
        if args.offline:
            judge = OfflineJudge(anthropic_judge_name(args.model, args.effort))
        else:
            judge = AnthropicJudge(model=args.model, effort=args.effort)
    if judge is not None and args.cache:
        cache = CachedJudge(judge, args.cache, offline=args.offline)
        judge = cache

    try:
        report = evaluate(spec, cases, judge)
    finally:
        if cache is not None:
            cache.save()

    if args.format == "json":
        print(render_json(report))
    else:
        print(render_text(report, verbose=args.verbose))
        if cache is not None:
            print(f"judge cache: {cache.hits} reused, {cache.misses} new")
    return EXIT_OK if report.ok else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
