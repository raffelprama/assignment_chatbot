"""One question in, one traceable answer out. Shared by the API, the CLI and the evaluation."""

import time
import uuid

from app.graph.state import RunOptions
from app.llm.usage import summarize
from app.services import Services


async def ask(
    services: Services, question: str, *, top_k: int | None = None, options: RunOptions | None = None
) -> dict:
    trace_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    state = await services.graph.ainvoke({
        "question": question.strip(),
        "top_k": top_k or services.settings.top_k,
        "options": options or {},
        "attempt": 0,
        "usage": [],
        "timings": [],
        "route": [],
    })
    timings: dict[str, float] = {}
    for entry in state.get("timings", []):
        timings[entry["node"]] = round(timings.get(entry["node"], 0.0) + entry["ms"], 1)
    timings["total"] = round((time.perf_counter() - started) * 1000, 1)
    normalized = state.get("normalized") or {}
    return {
        "trace_id": trace_id,
        "question": question,
        "status": state.get("status", "no_answer"),
        "answer": state.get("answer", ""),
        "citations": state.get("citations", []),
        "missing": state.get("missing") or None,
        "language": normalized.get("answer_language"),
        "intent": normalized.get("intent"),
        "search_query": normalized.get("search_query"),
        "judge": state.get("judge_status", "skipped"),
        "retrieved": [
            {key: item.get(key) for key in
             ("evidence_id", "score", "dense_rank", "sparse_rank", "best_dense_score", "matched_via")}
            for item in state.get("evidence", [])
        ],
        "invalid_citations": state.get("invalid_citations", []),
        "route": state.get("route", []),
        "usage": summarize(state.get("usage", [])),
        "timings_ms": timings,
    }
