"""Question-key CRUD.

Keys are the "Q" side of Q/A indexing: phrasings that point at a section. Adding a key is how an
operator fixes "this wording did not find the right SOP section" without editing the source
document, so the PDFs stay the single source of truth for answers.
"""

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_services
from app.errors import BadRequest, NotFound
from app.ingestion.indexer import index_single_key
from app.ingestion.pipeline import load_artifact, save_artifact
from app.schemas import KeyCreate
from app.services import Services

router = APIRouter(prefix="/rag/keys", tags=["question keys"])


def _key_view(record) -> dict:
    p = record.payload
    return {"key_id": str(record.id), "doc_id": p["doc_id"], "section_no": p["section_no"],
            "text": p["text"], "lang": p.get("key_lang"), "source": p.get("key_source")}


@router.get("")
async def list_keys(doc_id: str, section_no: int | None = None, services: Services = Depends(get_services)) -> dict:
    conditions: dict = {"doc_id": doc_id, "kind": "qkey"}
    if section_no is not None:
        conditions["section_no"] = section_no
    records = await services.store.scroll(conditions)
    items = sorted((_key_view(r) for r in records), key=lambda k: (k["section_no"], k["text"]))
    return {"items": items, "total": len(items)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_key(body: KeyCreate, services: Services = Depends(get_services)) -> dict:
    artifact = load_artifact(services.settings, body.doc_id)
    if artifact is None:
        raise NotFound(f"Document '{body.doc_id}' not found")
    if body.section_no not in {s["section_no"] for s in artifact["sections"]}:
        raise BadRequest(f"Document '{body.doc_id}' has no section {body.section_no}")
    bucket = artifact["keys"].setdefault(str(body.section_no), [])
    bucket.append({"text": body.text.strip(), "lang": body.lang, "source": "manual"})
    save_artifact(services.settings, artifact)
    key_id = await index_single_key(artifact, body.section_no, len(bucket) - 1, services.store, services.embedder)
    return {"key_id": key_id, "doc_id": body.doc_id, "section_no": body.section_no, "text": body.text.strip()}


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(key_id: str, services: Services = Depends(get_services)) -> Response:
    records = await services.store.get_points([key_id])
    if not records or records[0].payload.get("kind") != "qkey":
        raise NotFound(f"Question key '{key_id}' not found")
    payload = records[0].payload
    artifact = load_artifact(services.settings, payload["doc_id"])
    if artifact is not None:
        bucket = artifact["keys"].get(str(payload["section_no"]), [])
        if payload["key_index"] < len(bucket):
            bucket[payload["key_index"]]["removed"] = True  # keep the slot: point ids stay stable
            save_artifact(services.settings, artifact)
    await services.store.delete_points([key_id])
    return Response(status_code=status.HTTP_204_NO_CONTENT)
