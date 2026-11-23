"""The chat turn as a LangGraph state machine.

    normalize ──off_domain/unsafe──────────────────────────────────────────► respond
        │
    retrieve ─► answer ─► check_citations ──no valid citation / judge off──► respond
                                │
                              judge ──pass──────────────────────────────────► respond
                                │ incomplete/irrelevant (once): widen top_k ─► retrieve
                                │ unsupported (once): regenerate with feedback ► answer
                                └ still failing ───────────────────────────► respond (downgraded)
"""

import logging
import time
from functools import wraps

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.errors import ServiceUnavailable
from app.graph.citations import check_citations, strip_unknown_markers
from app.graph.schemas import AnswerDraft, JudgeVerdict, Normalized
from app.graph.state import ChatState
from app.graph.templates import render
from app.llm.prompts import load_prompt
from app.retrieval.hybrid import retrieve
from app.services import Services

log = logging.getLogger(__name__)


def _timed(name: str):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, state: ChatState) -> dict:
            started = time.perf_counter()
            update = await fn(self, state)
            update.setdefault("timings", []).append(
                {"node": name, "ms": round((time.perf_counter() - started) * 1000, 1)}
            )
            update.setdefault("route", []).append(name)
            return update
        return wrapper
    return decorator


def _evidence_block(evidence: list[dict]) -> str:
    blocks = []
    for item in evidence:
        section = (f"{item['section_no']}. {item['section_title']}" if item["kind"] == "section"
                   else "Peta dokumen / document overview")
        pages = ",".join(str(p) for p in item["pages"])
        blocks.append(
            f'<evidence id="{item["evidence_id"]}" document="{item["doc_title"]}" '
            f'section="{section}" page="{pages}">\n{item["text"]}\n</evidence>'
        )
    return "\n\n".join(blocks)


class ChatGraph:
    def __init__(self, services: Services):
        self.s = services
        self.cfg = services.settings
        self._prompts = {name: load_prompt(name) for name in ("normalize", "answer", "judge")}

    # ------------------------------------------------------------ nodes

    @_timed("normalize")
    async def normalize(self, state: ChatState) -> dict:
        system = self._prompts["normalize"].format(scope_card=self.s.catalog.scope_card())
        messages = [SystemMessage(system), HumanMessage(f"<question>\n{state['question']}\n</question>")]
        try:
            result = await self.s.llm.structured(Normalized, messages, node="normalize", model=self.cfg.model_fast)
        except ServiceUnavailable:
            # Later layers still protect the answer; refusing every question during an outage is wrong too.
            log.warning("normalize_unavailable; continuing as in_scope")
            fallback = {"intent": "in_scope", "search_query": state["question"],
                        "answer_language": "id", "reason": "normalize unavailable"}
            return {"normalized": fallback, "usage": []}
        return {"normalized": result.value.model_dump(), "usage": [result.usage]}

    @_timed("retrieve")
    async def retrieve(self, state: ChatState) -> dict:
        options = state.get("options") or {}
        normalized = state["normalized"]
        if options.get("full_context"):
            evidence = self.s.catalog.all_sections()
        elif normalized["intent"] == "catalog":
            evidence = self.s.catalog.doc_maps()
        else:
            evidence = await retrieve(
                self.s.store, self.s.embedder, normalized["search_query"],
                top_k=state["top_k"], pool=self.cfg.retrieval_pool, rrf_k=self.cfg.rrf_k,
                mode=options.get("mode", "hybrid"), kinds=options.get("kinds"),
                sparse_extra=state["question"],
            )
        return {"evidence": [e.to_dict() for e in evidence]}

    @_timed("answer")
    async def answer(self, state: ChatState) -> dict:
        normalized = state["normalized"]
        parts = [
            f"answer_language: {normalized['answer_language']}",
            f"<question>\n{state['question']}\n</question>",
            _evidence_block(state["evidence"]) or "(no evidence retrieved)",
        ]
        if state.get("feedback"):
            parts.append(f"A reviewer rejected your previous answer. Fix exactly this, using only the evidence:\n"
                         f"{state['feedback']}")
        messages = [SystemMessage(self._prompts["answer"]), HumanMessage("\n\n".join(parts))]
        result = await self.s.llm.structured(AnswerDraft, messages, node="answer", model=self.cfg.model_answer)
        return {"draft": result.value.model_dump(), "usage": [result.usage]}

    @_timed("check_citations")
    async def check_citations(self, state: ChatState) -> dict:
        draft = state["draft"]
        valid, invalid = check_citations(draft["citations"], state["evidence"])
        status = draft["status"]
        if status in ("answered", "partial") and not valid:
            status = "no_answer"  # never show an answer that cannot be traced to a source
        answer = strip_unknown_markers(draft["answer"], {c["evidence_id"] for c in valid})
        return {"citations": valid, "invalid_citations": invalid, "status": status,
                "answer": answer, "missing": draft.get("missing", "")}

    @_timed("judge")
    async def judge(self, state: ChatState) -> dict:
        content = "\n\n".join([
            f"<question>\n{state['question']}\n</question>",
            f"<answer status=\"{state['status']}\">\n{state['answer']}\n</answer>",
            f"<declared_missing>\n{state.get('missing') or '-'}\n</declared_missing>",
            _evidence_block(state["evidence"]),
        ])
        messages = [SystemMessage(self._prompts["judge"]), HumanMessage(content)]
        try:
            result = await self.s.llm.structured(JudgeVerdict, messages, node="judge", model=self.cfg.model_answer)
        except ServiceUnavailable:
            # Citations were already validated deterministically; the judge is a second opinion.
            return {"verdict": None, "judge_status": "unavailable", "usage": []}
        verdict = result.value.model_dump()
        return {"verdict": verdict, "judge_status": verdict["verdict"], "usage": [result.usage]}

    @_timed("plan_retry")
    async def plan_retry(self, state: ChatState) -> dict:
        verdict = state["verdict"]
        if verdict["verdict"] == "unsupported":
            claims = "; ".join(verdict["unsupported_claims"]) or verdict["reason"]
            return {"attempt": 1, "retry_reason": "unsupported",
                    "feedback": f"Remove or correct these unsupported claims: {claims}"}
        return {"attempt": 1, "retry_reason": verdict["verdict"],
                "top_k": max(state["top_k"], self.cfg.top_k_wide), "feedback": ""}

    @_timed("respond")
    async def respond(self, state: ChatState) -> dict:
        normalized = state.get("normalized") or {}
        language = normalized.get("answer_language", "id")
        intent = normalized.get("intent")
        if intent in ("off_domain", "unsafe"):
            kind = "out_of_scope" if intent == "off_domain" else "unsafe"
            return {"status": kind, "answer": render(kind, language, self.s.catalog.titles),
                    "citations": [], "missing": ""}
        status, answer = state.get("status", "no_answer"), state.get("answer", "")
        verdict = state.get("verdict")
        if verdict and verdict["verdict"] != "pass" and state.get("attempt", 0) >= 1:
            if verdict["verdict"] == "incomplete" and status == "answered":
                status = "partial"  # grounded but incomplete: keep it, flag what is missing
                extra = "; ".join(verdict["missing_aspects"])
                return {"status": status, "missing": "; ".join(filter(None, [state.get("missing"), extra]))}
            if verdict["verdict"] in ("unsupported", "irrelevant"):
                return {"status": "no_answer", "answer": render("unverified", language), "citations": []}
        if status == "no_answer":
            return {"answer": render("no_answer", language), "citations": []}
        return {}

    # ------------------------------------------------------------ routing

    @staticmethod
    def after_normalize(state: ChatState) -> str:
        return "respond" if state["normalized"]["intent"] in ("off_domain", "unsafe") else "retrieve"

    def after_check(self, state: ChatState) -> str:
        judge_on = (state.get("options") or {}).get("judge", self.cfg.judge_enabled)
        return "judge" if judge_on and state["status"] != "no_answer" else "respond"

    @staticmethod
    def after_judge(state: ChatState) -> str:
        verdict = state.get("verdict")
        if not verdict or verdict["verdict"] == "pass" or state.get("attempt", 0) >= 1:
            return "respond"
        return "plan_retry"

    @staticmethod
    def after_plan(state: ChatState) -> str:
        return "answer" if state["retry_reason"] == "unsupported" else "retrieve"

    def compile(self):
        graph = StateGraph(ChatState)
        for name in ("normalize", "retrieve", "answer", "check_citations", "judge", "plan_retry", "respond"):
            graph.add_node(name, getattr(self, name))
        graph.add_edge(START, "normalize")
        graph.add_conditional_edges("normalize", self.after_normalize, ["retrieve", "respond"])
        graph.add_edge("retrieve", "answer")
        graph.add_edge("answer", "check_citations")
        graph.add_conditional_edges("check_citations", self.after_check, ["judge", "respond"])
        graph.add_conditional_edges("judge", self.after_judge, ["plan_retry", "respond"])
        graph.add_conditional_edges("plan_retry", self.after_plan, ["answer", "retrieve"])
        graph.add_edge("respond", END)
        return graph.compile()


def attach_graph(services: Services) -> Services:
    services.graph = ChatGraph(services).compile()
    return services
