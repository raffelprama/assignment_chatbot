"""FastAPI application: `uvicorn app.main:app`."""

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import chat, documents, health, keys, search
from app.api.deps import require_api_key
from app.config import get_settings
from app.errors import AppError
from app.graph.build import attach_graph
from app.services import build_services

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    services = attach_graph(build_services(get_settings()))
    app.state.services = services
    yield
    await services.close()


def _error(status_code: int, code: str, message: str, request: Request, detail: object = None) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", None)
    body = {"error": code, "message": message, "detail": detail, "trace_id": trace_id}
    return JSONResponse(status_code=status_code, content=body)


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs every request URL at INFO, including the Qdrant cluster host; keep infra details out of logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = FastAPI(
        title="SOP Assistant",
        version="1.0.0",
        description="Question answering over SOP PDFs with checked citations (document, page, section).",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def trace(request: Request, call_next):
        request.state.trace_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.trace_id
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        log.warning("app_error code=%s message=%s", exc.code, exc.message)
        return _error(exc.status_code, exc.code, exc.message, request, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        detail = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
        return _error(422, "ValidationError", "Invalid request", request, detail)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return _error(exc.status_code, "HTTPError", str(exc.detail), request)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled_error")
        return _error(500, "InternalError", "Unexpected server error", request)

    protected = [Depends(require_api_key)]
    app.include_router(health.router)
    for module in (chat, documents, keys, search):
        app.include_router(module.router, prefix="/api/v1", dependencies=protected)
    return app


app = create_app()
