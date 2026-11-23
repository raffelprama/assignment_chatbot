"""Hybrid retrieval: dense + BM25 channels, reciprocal rank fusion, collapsed to citable units.

Fusion is done here rather than server-side so every result keeps its per-channel rank; the
evaluation uses those ranks to show which channel found what. A unit is a section (hit through
its own point or any of its question keys) or a document map.
"""

from dataclasses import asdict, dataclass, field
from typing import Literal

from app.llm.factory import Embedder
from app.retrieval.sparse import query_vector
from app.retrieval.store import VectorStore

Mode = Literal["hybrid", "dense", "sparse"]


@dataclass
class Evidence:
    evidence_id: str  # "KB_01 §4" or "KB_01 peta-dokumen"
    kind: str  # "section" | "docmap"
    doc_id: str
    label: str
    doc_title: str
    file_name: str
    pages: list[int]
    section_no: int | None
    section_title: str | None
    text: str
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None
    matched_via: list[str] = field(default_factory=list)
    best_dense_score: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def evidence_id(label: str, section_no: int | None, kind: str) -> str:
    return f"{label} peta-dokumen" if kind == "docmap" else f"{label} §{section_no}"


def _unit_key(payload: dict) -> tuple[str, str]:
    if payload["kind"] == "docmap":
        return payload["doc_id"], "docmap"
    return payload["doc_id"], f"s{payload['section_no']}"


def _new_evidence(payload: dict) -> Evidence:
    kind = "docmap" if payload["kind"] == "docmap" else "section"
    return Evidence(
        evidence_id=evidence_id(payload["label"], payload.get("section_no"), kind),
        kind=kind,
        doc_id=payload["doc_id"],
        label=payload["label"],
        doc_title=payload["doc_title"],
        file_name=payload["file_name"],
        pages=payload.get("pages", []),
        section_no=payload.get("section_no") if kind == "section" else None,
        section_title=payload.get("section_title") if kind == "section" else None,
        text=payload["section_text"],
        score=0.0,
    )


def fuse(channels: dict[str, list], rrf_k: int) -> list[Evidence]:
    units: dict[tuple[str, str], Evidence] = {}
    for channel, points in channels.items():
        seen_units: set[tuple[str, str]] = set()
        for rank, point in enumerate(points, start=1):
            key = _unit_key(point.payload)
            unit = units.setdefault(key, _new_evidence(point.payload))
            if point.payload["kind"] not in unit.matched_via:
                unit.matched_via.append(point.payload["kind"])
            if channel == "dense" and (unit.best_dense_score is None or point.score > unit.best_dense_score):
                unit.best_dense_score = round(point.score, 4)
            if key in seen_units:  # a unit scores once per channel, at its best rank
                continue
            seen_units.add(key)
            unit.score += 1.0 / (rrf_k + rank)
            if channel == "dense":
                unit.dense_rank = len(seen_units)
            else:
                unit.sparse_rank = len(seen_units)
    ranked = sorted(units.values(), key=lambda e: e.score, reverse=True)
    for item in ranked:
        item.score = round(item.score, 6)
    return ranked


async def retrieve(
    store: VectorStore,
    embedder: Embedder,
    query: str,
    *,
    top_k: int,
    pool: int,
    rrf_k: int,
    mode: Mode = "hybrid",
    kinds: list[str] | None = None,
    sparse_extra: str = "",
) -> list[Evidence]:
    """`sparse_extra` adds terms to the BM25 query only (e.g. the user's original wording)."""
    dense = await embedder.embed_query(query) if mode in ("hybrid", "dense") else None
    sparse = query_vector(f"{query} {sparse_extra}") if mode in ("hybrid", "sparse") else None
    channels = await store.query_channels(dense, sparse, pool, kinds)
    return fuse(channels, rrf_k)[:top_k]
