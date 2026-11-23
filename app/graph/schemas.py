"""Structured outputs the LLM steps must return (validated by the schema, not parsed by hand)."""

from typing import Literal

from pydantic import BaseModel, Field


class Normalized(BaseModel):
    intent: Literal["in_scope", "catalog", "off_domain", "unsafe"]
    search_query: str = Field(description="Standalone search query in Indonesian.")
    answer_language: str = Field(description="ISO 639-1 code of the user's language.")
    reason: str


class CitationDraft(BaseModel):
    evidence_id: str = Field(description='Evidence id exactly as given, e.g. "KB_01 §4".')
    quote: str = Field(description="Verbatim span copied from that evidence.")


class AnswerDraft(BaseModel):
    status: Literal["answered", "partial", "no_answer"]
    answer: str
    citations: list[CitationDraft]
    missing: str = Field(default="", description="What the documents do not specify (for partial).")


class JudgeVerdict(BaseModel):
    verdict: Literal["pass", "unsupported", "incomplete", "irrelevant"]
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_aspects: list[str] = Field(default_factory=list)
    reason: str
