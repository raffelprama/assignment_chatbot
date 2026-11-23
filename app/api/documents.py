"""Document CRUD and ingestion jobs."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile, status

from app.api.deps import get_services
from app.errors import AppError, NotFound
from app.ids import doc_id_from_filename
from app.ingestion.pipeline import artifact_path, load_artifact
from app.ingestion.service import check_pdf, ingest_pdf
from app.schemas import JobAccepted
from app.services import Services

log = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["documents"])


async def _run_job(services: Services, job_id: str, data: bytes, file_name: str, rebuild: bool) -> None:
    try:
        report = await ingest_pdf(services, data, file_name, rebuild=rebuild)
        services.catalog.refresh()
        services.registry.finish_job(job_id, status="completed", report=report)
    except AppError as exc:
        services.registry.finish_job(job_id, status="failed", error=f"{exc.message}: {exc.detail}")
    except Exception as exc:  # a background job must record every failure, never vanish
        log.exception("ingestion_job_crashed job=%s", job_id)
        services.registry.finish_job(job_id, status="failed", error=type(exc).__name__)


def _start_job(services: Services, tasks: BackgroundTasks, data: bytes, file_name: str, rebuild: bool) -> dict:
    job_id = uuid.uuid4().hex
    doc_id = doc_id_from_filename(file_name)
    services.registry.create_job(job_id, doc_id, file_name)
    tasks.add_task(_run_job, services, job_id, data, file_name, rebuild)
    return {"job_id": job_id, "doc_id": doc_id, "status": "processing"}


@router.post("/documents", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
async def upload_document(
    tasks: BackgroundTasks, file: UploadFile = File(...), services: Services = Depends(get_services)
) -> dict:
    """Upload a PDF. Extraction, indexing and the smoke test run in the background; poll the job."""
    data = await file.read()
    file_name = file.filename or "document.pdf"
    check_pdf(data, file_name, services.settings.max_upload_mb)
    return _start_job(services, tasks, data, file_name, rebuild=True)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, services: Services = Depends(get_services)) -> dict:
    job = services.registry.get_job(job_id)
    if job is None:
        raise NotFound(f"Job '{job_id}' not found")
    return job


@router.get("/documents")
async def list_documents(services: Services = Depends(get_services)) -> dict:
    documents = services.registry.list_documents()
    return {"items": documents, "total": len(documents)}


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, services: Services = Depends(get_services)) -> dict:
    artifact = load_artifact(services.settings, doc_id)
    if artifact is None:
        raise NotFound(f"Document '{doc_id}' not found")
    return {
        "doc_id": artifact["doc_id"],
        "title": artifact["title"],
        "file_name": artifact["file_name"],
        "sha256": artifact["sha256"],
        "pages": [{k: p[k] for k in ("page_no", "method", "layout", "route_reason")} for p in artifact["pages"]],
        "sections": artifact["sections"],
        "doc_map": artifact["doc_map"],
        "report": artifact["report"],
    }


@router.post("/documents/{doc_id}/reindex", status_code=status.HTTP_202_ACCEPTED, response_model=JobAccepted)
async def reindex_document(
    doc_id: str, tasks: BackgroundTasks, rebuild: bool = False, services: Services = Depends(get_services)
) -> dict:
    """Re-index from the stored upload. `rebuild=true` also re-runs extraction and key generation."""
    artifact = load_artifact(services.settings, doc_id)
    if artifact is None:
        raise NotFound(f"Document '{doc_id}' not found")
    upload = services.settings.data_dir / "uploads" / f"{artifact['sha256']}.pdf"
    if not upload.exists():
        kb_copy = services.settings.data_dir / "kb" / artifact["file_name"]
        upload = kb_copy if kb_copy.exists() else upload
    if not upload.exists():
        raise NotFound(f"Original PDF for '{doc_id}' is not stored; upload it again")
    return _start_job(services, tasks, upload.read_bytes(), artifact["file_name"], rebuild=rebuild)


@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str, services: Services = Depends(get_services)) -> Response:
    """Delete a document's points, artefact and registry entry."""
    path = artifact_path(services.settings, doc_id)
    if not path.exists() and services.registry.get_document(doc_id) is None:
        raise NotFound(f"Document '{doc_id}' not found")
    await services.store.delete_doc(doc_id)
    path.unlink(missing_ok=True)
    services.registry.delete_document(doc_id)
    services.catalog.remove(doc_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
