"""Artefact -> Qdrant points (write the new version, verify, then delete older versions)."""

import logging

from qdrant_client import models

from app.ids import point_id
from app.llm.factory import Embedder
from app.retrieval.hybrid import evidence_id, retrieve
from app.retrieval.sparse import document_vector
from app.retrieval.store import DENSE, SPARSE, VectorStore

log = logging.getLogger(__name__)

# Fixed average length for BM25 length normalisation, so documents indexed at different times
# are scored on the same scale (sections are ~45 tokens, question keys ~6).
BM25_AVG_DOC_LEN = 30.0


def _units(artifact: dict) -> list[tuple[str, dict]]:
    """(text to index, payload) for every point of the artefact."""
    base = {
        "doc_id": artifact["doc_id"],
        "label": artifact["label"],
        "doc_title": artifact["title"],
        "file_name": artifact["file_name"],
        "version": artifact["sha256"],
    }
    units = []
    for section in artifact["sections"]:
        section_payload = {
            **base,
            "section_no": section["section_no"],
            "section_title": section["title"],
            "pages": section["pages"],
            "section_text": section["text"],
        }
        indexed = f"{artifact['title']} — {section['title']}\n{section['text']}"
        units.append((indexed, {**section_payload, "kind": "section", "key_index": None}))
        for index, key in enumerate(artifact["keys"].get(str(section["section_no"]), [])):
            if key.get("removed"):  # removed keys keep their slot so point ids stay stable
                continue
            units.append((key["text"], {
                **section_payload, "kind": "qkey", "key_index": index,
                "key_lang": key["lang"], "key_source": key.get("source", "generated"),
            }))
    all_pages = sorted({p for s in artifact["sections"] for p in s["pages"]})
    units.append((artifact["doc_map"], {
        **base, "kind": "docmap", "section_no": None, "section_title": None, "pages": all_pages,
        "section_text": artifact["doc_map"], "key_index": None,
    }))
    return units


def _point_id(payload: dict) -> str:
    return point_id(payload["version"], payload["kind"], payload["section_no"], payload["key_index"])


async def index_single_key(artifact: dict, section_no: int, key_index: int,
                           store: VectorStore, embedder: Embedder) -> str:
    """Embed and upsert one question key (manual keys added through the API)."""
    unit = next(
        (text, payload) for text, payload in _units(artifact)
        if payload["kind"] == "qkey" and payload["section_no"] == section_no and payload["key_index"] == key_index
    )
    text, payload = unit
    dense = (await embedder.embed_documents([text]))[0]
    indices, values = document_vector(text, BM25_AVG_DOC_LEN)
    pid = _point_id(payload)
    await store.upsert([models.PointStruct(
        id=pid,
        vector={DENSE: dense, SPARSE: models.SparseVector(indices=indices, values=values)},
        payload={**payload, "text": text},
    )])
    return pid


async def index_artifact(artifact: dict, store: VectorStore, embedder: Embedder) -> dict:
    units = _units(artifact)
    texts = [text for text, _ in units]
    vectors = await embedder.embed_documents(texts)
    points = []
    for (text, payload), dense in zip(units, vectors):
        indices, values = document_vector(text, BM25_AVG_DOC_LEN)
        points.append(models.PointStruct(
            id=_point_id(payload),
            vector={DENSE: dense, SPARSE: models.SparseVector(indices=indices, values=values)},
            payload={**payload, "text": text},
        ))
    await store.ensure_collection(embedder.dim)
    await store.upsert(points)
    smoke = await smoke_test(artifact, store, embedder)
    if smoke["failed"]:
        log.warning("smoke_test_failed doc=%s failures=%s", artifact["doc_id"], smoke["failed"])
    await store.delete_doc(artifact["doc_id"], keep_version=artifact["sha256"])
    kinds = {}
    for _, payload in units:
        kinds[payload["kind"]] = kinds.get(payload["kind"], 0) + 1
    return {"points": len(points), "by_kind": kinds, "smoke_test": smoke}


async def smoke_test(artifact: dict, store: VectorStore, embedder: Embedder) -> dict:
    """Each section's own title must retrieve that section in the top 3 (one green light is not proof)."""
    failed = []
    for section in artifact["sections"]:
        if section["section_no"] is None:
            continue
        query = f"{artifact['title']} {section['title']}"
        hits = await retrieve(store, embedder, query, top_k=3, pool=20, rrf_k=60)
        expected = evidence_id(artifact["label"], section["section_no"], "section")
        if expected not in [h.evidence_id for h in hits]:
            failed.append(expected)
    return {"checked": sum(1 for s in artifact["sections"] if s["section_no"] is not None), "failed": failed}
