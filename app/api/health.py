from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.deps import get_services
from app.errors import ServiceUnavailable
from app.services import Services

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready(services: Services = Depends(get_services)):
    cfg = services.settings
    try:
        exists = await services.store.exists()
        points = await services.store.count() if exists else 0
    except ServiceUnavailable as exc:
        return JSONResponse(status_code=503, content={"status": "unavailable", "qdrant": exc.message})
    body = {
        "status": "ready" if points else "empty",
        "collection": cfg.collection,
        "points": points,
        "documents": services.catalog.titles,
        "models": {"answer": cfg.model_answer, "fast": cfg.model_fast, "fallbacks": cfg.model_fallbacks,
                   "embedding": cfg.embedding_model},
    }
    return JSONResponse(status_code=200 if points else 503, content=body)
