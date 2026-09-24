"""Measure Jev against hand-labelled postings before relying on its notes.

Run from the project root:

    .venv/bin/python scripts/eval_prefill.py [--data data/labelled_postings.jsonl]

Each line of the data file is {"lang": "zh"|"en", "text": <posting>, "labels": {question: answer}},
where a question is one of the Jev posting questions (track, degree, chinese_level, start_timing:
a label; restricted, pays_fee, mostly_annotation, mostly_sales: true or false). Label as many
questions per posting as you like. Copy data/labelled_postings.example.jsonl to start; the real
file is gitignored.

The script uses TypeSafe whenever a key is on this machine, even with provider: none, so you can
measure Jev before switching it on. It prints accuracy per question and language, and accuracy
among the answers that clear the thresholds in config/decisions.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from internship_os.config import load_config
from internship_os.decision_provider import NullProvider, ask_safely, get_provider, load_decisions
from internship_os.jev import posting_questions

DEFAULT_DATA = Path("data/labelled_postings.jsonl")


def validate_row(row: object) -> str | None:
    """None when the row is usable, else the problem."""
    if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"].strip():
        return "needs a non-empty 'text'"
    if row.get("lang") not in ("zh", "en"):
        return "'lang' must be zh or en"
    labels = row.get("labels")
    if not isinstance(labels, dict) or not labels:
        return "needs a non-empty 'labels' object"
    questions = posting_questions()
    for key, gold in labels.items():
        question = questions.get(key)
        if question is None:
            return f"unknown question {key!r}; use one of {', '.join(questions)}"
        if question["type"] == "noul" and not isinstance(gold, bool):
            return f"{key} needs true or false, got {gold!r}"
        if question["type"] == "choice" and gold not in question["criteria"]:
            return f"{key} needs one of {', '.join(question['criteria'])}, got {gold!r}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    args = parser.parse_args(argv)

    if not args.data.exists():
        sys.exit(f"{args.data} not found. Copy data/labelled_postings.example.jsonl and label real postings.")
    rows = []
    for number, line in enumerate(args.data.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.exit(f"row {number}: not JSON ({exc})")
        problem = validate_row(row)
        if problem:
            sys.exit(f"row {number}: {problem}")
        rows.append(row)

    config = load_config()
    cfg = load_decisions(config.root)
    provider = get_provider(config, force=True)
    if isinstance(provider, NullProvider):
        sys.exit(f"Jev is off: {provider.reason}. Put TYPESAFE_API_KEY in .env or your shell.")

    questions = posting_questions()
    overall = defaultdict(lambda: [0, 0])  # (question, lang) -> [correct, total]
    confident = defaultdict(lambda: [0, 0])  # (question, lang) -> [correct, total] above the thresholds
    failed = 0
    model = provider.model
    for row in rows:
        asked = {key: questions[key] for key in row["labels"]}
        batch, error = ask_safely(provider, {"posting": row["text"]}, asked)
        if batch is None:
            failed += 1
            print(f"# a row failed: {error}")
            continue
        model = batch.model
        for key, gold in row["labels"].items():
            decision = batch.decisions.get(key)
            if decision is None:
                continue
            if decision.kind == "noul":
                predicted = decision.value >= 0.5
                sure = decision.value >= cfg.noul_flag_p or decision.value <= 1 - cfg.noul_flag_p
            else:
                predicted = decision.value
                sure = (decision.confidence or 0.0) >= cfg.choice_min_confidence
            hit = int(predicted == gold)
            for lang in (row["lang"], "all"):
                overall[(key, lang)][0] += hit
                overall[(key, lang)][1] += 1
                if sure:
                    confident[(key, lang)][0] += hit
                    confident[(key, lang)][1] += 1

    print(f"# model {model}; {len(rows)} postings, {failed} failed")
    print(f"# thresholds: noul_flag_p {cfg.noul_flag_p}, choice_min_confidence {cfg.choice_min_confidence}")
    print(f"{'question':<20}{'lang':<6}{'all':>10}{'acc':>7}{'confident':>12}{'acc':>7}")
    for key, lang in sorted(overall):
        ok, total = overall[(key, lang)]
        c_ok, c_total = confident[(key, lang)]
        c_acc = f"{c_ok / c_total:.2f}" if c_total else "-"
        print(f"{key:<20}{lang:<6}{f'{ok}/{total}':>10}{ok / total:>7.2f}{f'{c_ok}/{c_total}':>12}{c_acc:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
