"""HTTP request/response models."""

from typing import Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: object | None = None
    trace_id: str | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=10)


class Citation(BaseModel):
    evidence_id: str
    doc_id: str
    doc_title: str
    file_name: str
    pages: list[int]
    section_no: int | None
    section_title: str | None
    quote: str


class Retrieved(BaseModel):
    evidence_id: str
    score: float
    dense_rank: int | None
    sparse_rank: int | None
    best_dense_score: float | None
    matched_via: list[str]


class ChatResponse(BaseModel):
    trace_id: str
    question: str
    status: Literal["answered", "partial", "no_answer", "out_of_scope", "unsafe"]
    answer: str
    citations: list[Citation]
    missing: str | None
    language: str | None
    intent: str | None
    search_query: str | None
    judge: str
    retrieved: list[Retrieved]
    route: list[str]
    usage: dict
    timings_ms: dict[str, float]


class JobAccepted(BaseModel):
    job_id: str
    doc_id: str
    status: str = "processing"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: Literal["hybrid", "dense", "sparse"] = "hybrid"


class KeyCreate(BaseModel):
    doc_id: str
    section_no: int = Field(ge=1)
    text: str = Field(min_length=3, max_length=300)
    lang: str = Field(default="id", max_length=5)
