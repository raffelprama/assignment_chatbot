"""Retrieval-only ablations (no LLM calls): which channel and which index units earn their place.

Replays every question that has expected sections through several retrieval configurations, using
the normalized search query recorded in a previous end-to-end run (default: `baseline`) and, for
comparison, the user's raw question. Reports Hit@k (any expected section retrieved) and Recall@k
(share of expected sections retrieved) at k = 3, 5, 8.

    python -m eval.retrieval_eval            # writes eval/reports/retrieval.md
"""

import argparse
import asyncio
import json
import statistics
from pathlib import Path

from app.config import get_settings
from app.retrieval.hybrid import retrieve
from app.services import build_services
from eval.run import REPORTS, load_questions

CONFIGS = [
    # name, mode, kinds, query source
    ("hybrid · all units · normalized query", "hybrid", None, "normalized"),
    ("dense only · all units · normalized query", "dense", None, "normalized"),
    ("BM25 only · all units · normalized query", "sparse", None, "normalized"),
    ("hybrid · sections only (no question keys / doc maps)", "hybrid", ["section"], "normalized"),
    ("hybrid · sections + doc maps (no question keys)", "hybrid", ["section", "docmap"], "normalized"),
    ("hybrid · all units · raw user question", "hybrid", None, "raw"),
]
KS = (3, 5, 8)


def _queries(run_name: str) -> dict[str, str]:
    path = REPORTS / "runs" / f"{run_name}.jsonl"
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {r["id"]: r["result"].get("search_query") for r in rows if r["result"].get("search_query")}


async def evaluate(run_name: str) -> list[dict]:
    settings = get_settings()
    services = build_services(settings)
    normalized = _queries(run_name)
    questions = [q for q in load_questions() if q["expected_sections"]]
    results = []
    try:
        for name, mode, kinds, source in CONFIGS:
            hits = {k: [] for k in KS}
            recalls = {k: [] for k in KS}
            per_question = {}
            for q in questions:
                query = normalized.get(q["id"], q["question"]) if source == "normalized" else q["question"]
                ranked = await retrieve(services.store, services.embedder, query, top_k=max(KS),
                                        pool=settings.retrieval_pool, rrf_k=settings.rrf_k, mode=mode,
                                        kinds=kinds, sparse_extra=q["question"] if source == "normalized" else "")
                ids = [e.evidence_id for e in ranked]
                expected = set(q["expected_sections"])
                for k in KS:
                    found = expected & set(ids[:k])
                    hits[k].append(1.0 if found else 0.0)
                    recalls[k].append(len(found) / len(expected))
                per_question[q["id"]] = len(expected & set(ids[:3])) / len(expected)
            results.append({
                "config": name,
                "n": len(questions),
                **{f"hit@{k}": round(statistics.mean(hits[k]), 3) for k in KS},
                **{f"recall@{k}": round(statistics.mean(recalls[k]), 3) for k in KS},
                "misses_at_3": sorted(qid for qid, r in per_question.items() if r < 1),
            })
    finally:
        await services.close()
    return results


def render(results: list[dict], run_name: str) -> str:
    lines = ["# Retrieval evaluation (no LLM)", "",
             f"Questions with expected sections: {results[0]['n']}. Normalized queries come from run `{run_name}`.", "",
             "| Configuration | Hit@3 | Recall@3 | Recall@5 | Recall@8 | Questions not fully covered at k=3 |",
             "|---|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r['config']} | {r['hit@3']:.2f} | {r['recall@3']:.2f} | {r['recall@5']:.2f} | "
                     f"{r['recall@8']:.2f} | {', '.join(r['misses_at_3']) or '-'} |")
    lines += ["", "Hit@k = at least one expected section in the top k. Recall@k = share of expected sections in the "
              "top k (multi-section questions need all of them).", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default="baseline", help="run whose normalized queries to replay")
    args = parser.parse_args()
    results = asyncio.run(evaluate(args.run))
    report = render(results, args.run)
    (REPORTS / "retrieval.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
