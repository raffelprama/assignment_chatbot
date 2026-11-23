"""Graph state. List fields with `operator.add` accumulate across nodes (usage, timings, route)."""

import operator
from typing import Annotated, Any, TypedDict

from app.llm.usage import Usage


class RunOptions(TypedDict, total=False):
    mode: str  # retrieval channel: "hybrid" | "dense" | "sparse"
    kinds: list[str] | None  # restrict point kinds (ablation: sections only)
    judge: bool
    full_context: bool  # ablation: give the answer step every section instead of retrieving


class ChatState(TypedDict, total=False):
    question: str
    top_k: int
    options: RunOptions
    normalized: dict[str, Any]
    evidence: list[dict[str, Any]]
    draft: dict[str, Any]
    citations: list[dict[str, Any]]
    invalid_citations: list[dict[str, Any]]
    status: str
    answer: str
    missing: str
    verdict: dict[str, Any] | None
    judge_status: str
    attempt: int
    retry_reason: str
    feedback: str
    usage: Annotated[list[Usage], operator.add]
    timings: Annotated[list[dict[str, Any]], operator.add]
    route: Annotated[list[str], operator.add]
