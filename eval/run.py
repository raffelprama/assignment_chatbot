"""End-to-end evaluation over eval/questions.jsonl.

    python -m eval.run --name baseline
    python -m eval.run --name no_judge --no-judge
    python -m eval.run --name full_context --full-context
    python -m eval.run --name top5 --top-k 5
    python -m eval.run --name baseline_r2 --ids A1,H1,U1      # subset (e.g. stability re-runs)

Writes eval/reports/runs/<name>.jsonl (raw responses + checks) and eval/reports/<name>.md.
A question is `correct` when its status is acceptable, every required fact appears, and nothing
forbidden (an invented number, a "not required" drawn from silence, ...) appears.
"""

import argparse
import asyncio
import json
import logging
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

from app.chat import ask
from app.config import get_settings
from app.errors import ServiceUnavailable
from app.graph.build import attach_graph
from app.services import build_services

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"


def load_questions(ids: set[str] | None = None, file: str = "questions.jsonl") -> list[dict]:
    lines = (ROOT / file).read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line) for line in lines if line.strip()]
    return [q for q in questions if not ids or q["id"] in ids]


_NEGATION_CUES = ("tidak", "bukan", "belum", "tanpa", "apakah", "not ", "no ", "whether", "if ")


def _affirmative_match(pattern: str, text: str) -> bool:
    """A forbidden pattern counts only when asserted: a match whose sentence has a negation cue before
    it ("dokumen tidak menyatakan bahwa P1 sama dengan SEV1") is the honest answer, not a claim.
    Known leniency: an affirmative claim placed after an unrelated negation in the same sentence is missed."""
    for match in re.finditer(pattern, text):
        sentence_start = max(text.rfind(". ", 0, match.start()), text.rfind("\n", 0, match.start())) + 1
        if not any(cue in text[sentence_start:match.start()] for cue in _NEGATION_CUES):
            return True
    return False


def score(question: dict, result: dict) -> dict:
    text = f"{result['answer']} {result.get('missing') or ''}".lower()
    status_ok = result["status"] in question["expected_status"]
    facts_ok = all(any(alt.lower() in text for alt in group) for group in question.get("must_include", []))
    ideal = question.get("ideal_include")
    ideal_ok = None if not ideal else all(any(a.lower() in text for a in g) for g in ideal)
    forbidden = [s for s in question.get("must_not_include", []) if s.lower() in text]
    forbidden += [rx for rx in question.get("must_not_regex", []) if _affirmative_match(rx, text)]
    retrieved = [item["evidence_id"] for item in result["retrieved"]]
    expected = question["expected_sections"]
    recall = len(set(expected) & set(retrieved)) / len(expected) if expected else None
    correct = status_ok and facts_ok and not forbidden
    return {
        "correct": correct,
        "status_ok": status_ok,
        "facts_ok": facts_ok,
        "ideal_ok": ideal_ok,
        "forbidden_hits": forbidden,
        "retrieval_recall": recall,
        "failure": "" if correct else _failure(question, result, status_ok, facts_ok, forbidden, recall),
    }


def _failure(question, result, status_ok, facts_ok, forbidden, recall) -> str:
    if forbidden:
        return "hallucination"
    refused = result["status"] in ("no_answer", "out_of_scope", "unsafe")
    expects_answer = any(s in ("answered", "partial") for s in question["expected_status"])
    if recall is not None and recall < 1 and (refused or not facts_ok):
        return "retrieval_miss"
    if refused and expects_answer and not status_ok:
        return "wrong_refusal"
    if not facts_ok:
        return "incomplete"
    return "wrong_status"


async def _ask_and_score(services, question: dict, top_k: int | None, options: dict) -> dict:
    try:
        result = await ask(services, question["question"], top_k=top_k, options=options)
        checks = score(question, result)
    except ServiceUnavailable as exc:
        result = {"status": "error", "answer": "", "error": f"{exc.message}: {exc.detail}"}
        checks = {"correct": False, "failure": "error", "retrieval_recall": None}
    flag = "ok " if checks["correct"] else f"FAIL[{checks['failure']}]"
    print(f"{question['id']:5s} {flag:22s} {result['status']:13s} {result.get('answer', '')[:90]}", flush=True)
    return {"id": question["id"], "group": question["group"], "question": question["question"],
            "expected_status": question["expected_status"], "result": result, "checks": checks}


async def run(name: str, ids: set[str] | None, top_k: int | None, options: dict,
              questions_file: str = "questions.jsonl") -> list[dict]:
    """One pass over the questions, then one more attempt for questions that hit a provider error.
    First-pass errors are kept in `first_pass_error` so overload stays visible in the report."""
    services = attach_graph(build_services(get_settings()))
    questions = load_questions(ids, questions_file)
    rows = []
    try:
        for question in questions:
            rows.append(await _ask_and_score(services, question, top_k, options))
        for index, row in enumerate(rows):
            if row["result"]["status"] == "error":
                await asyncio.sleep(20)
                retried = await _ask_and_score(services, questions[index], top_k, options)
                retried["first_pass_error"] = row["result"].get("error")
                rows[index] = retried
    finally:
        await services.close()
    out = REPORTS / "runs" / f"{name}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return rows


def _pct(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p * (len(ordered) - 1))))] if ordered else 0.0


def summarize(rows: list[dict]) -> dict:
    ok_rows = [r for r in rows if r["result"]["status"] != "error"]
    groups: dict[str, list[int]] = {}
    for row in rows:
        stats = groups.setdefault(row["group"], [0, 0])
        stats[0] += int(row["checks"]["correct"])
        stats[1] += 1
    totals = [r["result"]["timings_ms"]["total"] for r in ok_rows]
    recalls = [r["checks"]["retrieval_recall"] for r in ok_rows if r["checks"]["retrieval_recall"] is not None]
    usage = [r["result"]["usage"] for r in ok_rows]
    node_ms: dict[str, list[float]] = {}
    for row in ok_rows:
        for node, ms in row["result"]["timings_ms"].items():
            node_ms.setdefault(node, []).append(ms)
    return {
        "questions": len(rows),
        "correct": sum(r["checks"]["correct"] for r in rows),
        "by_group": {g: f"{c}/{t}" for g, (c, t) in groups.items()},
        "failures": dict(Counter(r["checks"]["failure"] for r in rows if r["checks"]["failure"])),
        "hallucinations": sum(1 for r in rows if r["checks"].get("failure") == "hallucination"),
        "errors": sum(1 for r in rows if r["result"]["status"] == "error"),
        "errors_first_pass": sum(1 for r in rows if r["result"]["status"] == "error" or r.get("first_pass_error")),
        "statuses": dict(Counter(r["result"]["status"] for r in rows)),
        "judge": dict(Counter(r["result"].get("judge", "-") for r in ok_rows)),
        "retries": sum(1 for r in ok_rows if r["result"]["route"].count("answer") > 1),
        "invalid_citations_removed": sum(len(r["result"].get("invalid_citations", [])) for r in ok_rows),
        "mean_retrieval_recall": round(statistics.mean(recalls), 3) if recalls else None,
        "latency_ms": {"p50": round(_pct(totals, 0.5)), "p95": round(_pct(totals, 0.95)),
                       "max": round(max(totals)) if totals else 0},
        "node_p50_ms": {n: round(_pct(v, 0.5)) for n, v in node_ms.items() if n != "total"},
        "llm_calls_per_question": round(statistics.mean(u["llm_calls"] for u in usage), 2) if usage else 0,
        "tokens_per_question": {
            "input": round(statistics.mean(u["input_tokens"] for u in usage)) if usage else 0,
            "output": round(statistics.mean(u["output_tokens"] for u in usage)) if usage else 0,
        },
        "cost_usd_total": round(sum(u["cost_usd"] for u in usage), 5),
        "cost_usd_per_question": round(sum(u["cost_usd"] for u in usage) / max(1, len(usage)), 6),
        "unpriced_calls": sum(u.get("unpriced_calls", 0) for u in usage),
        "models": sorted({m for u in usage for m in u.get("models", [])}),
    }


def render(name: str, options: dict, summary: dict, rows: list[dict]) -> str:
    lines = [f"# Evaluation run: `{name}`", "", f"Options: `{json.dumps(options)}`", "",
             "## Summary", "", "```json", json.dumps(summary, indent=2, ensure_ascii=False), "```", "",
             "## Per question", "",
             "| id | group | status | expected | ok | failure | cited | retrieval recall | ideal | ms |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        r, c = row["result"], row["checks"]
        cited = ", ".join(x["evidence_id"] for x in r.get("citations", [])) or "-"
        recall = "-" if c.get("retrieval_recall") is None else f"{c['retrieval_recall']:.2f}"
        ideal = {None: "-", True: "yes", False: "no"}[c.get("ideal_ok")]
        ms = r.get("timings_ms", {}).get("total", 0)
        lines.append(f"| {row['id']} | {row['group']} | {r['status']} | {'/'.join(row['expected_status'])} | "
                     f"{'✅' if c['correct'] else '❌'} | {c['failure'] or '-'} | {cited} | {recall} | {ideal} | {ms:.0f} |")
    lines += ["", "## Answers", ""]
    for row in rows:
        r = row["result"]
        lines.append(f"**{row['id']} — {row['question']}**  \n`{r['status']}` · {r.get('answer', '')}")
        if r.get("missing"):
            lines.append(f"  \n_Not specified:_ {r['missing']}")
        lines.append("")
    return "\n".join(lines)


def rescore(name: str, questions_file: str) -> None:
    """Apply the current checks to a saved run (used after fixing a faulty check)."""
    path = REPORTS / "runs" / f"{name}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    questions = {q["id"]: q for q in load_questions(file=questions_file)}
    for row in rows:
        if row["result"]["status"] != "error":
            row["checks"] = score(questions[row["id"]], row["result"])
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    summary = summarize(rows)
    options = {"rescored": True}
    (REPORTS / f"{name}.md").write_text(render(name, options, summary, rows), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("correct", "questions", "by_group", "failures", "hallucinations")},
                     ensure_ascii=False))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True)
    parser.add_argument("--ids", help="comma-separated question ids")
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--mode", choices=["hybrid", "dense", "sparse"], default="hybrid")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--full-context", action="store_true", help="give the answer step every section")
    parser.add_argument("--questions", default="questions.jsonl", help="question file inside eval/")
    parser.add_argument("--rescore", action="store_true",
                        help="re-score a saved run with the current checks (no LLM calls)")
    args = parser.parse_args()
    if args.rescore:
        rescore(args.name, args.questions)
        return
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    options = {"mode": args.mode, "judge": not args.no_judge, "full_context": args.full_context}
    ids = set(args.ids.split(",")) if args.ids else None
    rows = asyncio.run(run(args.name, ids, args.top_k, options, args.questions))
    summary = summarize(rows)
    report = render(args.name, {**options, "top_k": args.top_k}, summary, rows)
    (REPORTS / f"{args.name}.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
