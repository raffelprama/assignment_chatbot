from fastapi import APIRouter, Depends

from app.api.deps import get_services
from app.retrieval.hybrid import retrieve
from app.schemas import SearchRequest
from app.services import Services

router = APIRouter(prefix="/rag", tags=["search"])


@router.post("/search")
async def search(body: SearchRequest, services: Services = Depends(get_services)) -> dict:
    """Retrieval only, no LLM: shows what each channel finds (for debugging and evaluation)."""
    cfg = services.settings
    hits = await retrieve(services.store, services.embedder, body.query, top_k=body.top_k,
                          pool=cfg.retrieval_pool, rrf_k=cfg.rrf_k, mode=body.mode)
    return {"query": body.query, "mode": body.mode, "items": [h.to_dict() for h in hits]}
