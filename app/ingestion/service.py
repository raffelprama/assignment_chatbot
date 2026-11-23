"""Ingest one PDF end to end: artefact (reused when the file is unchanged) -> index -> registry."""

import logging

from app.errors import BadRequest, FileTooLarge, UnsupportedFile
from app.ids import doc_id_from_filename, sha256_bytes
from app.ingestion.indexer import index_artifact
from app.ingestion.pipeline import build_artifact, load_artifact, save_artifact
from app.services import Services

log = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"


def check_pdf(data: bytes, file_name: str, max_mb: int) -> None:
    if not data:
        raise BadRequest(f"'{file_name}' is empty")
    if len(data) > max_mb * 1024 * 1024:
        raise FileTooLarge(f"'{file_name}' exceeds {max_mb} MB")
    if not data.startswith(PDF_MAGIC):
        raise UnsupportedFile(f"'{file_name}' is not a PDF")


async def ingest_pdf(services: Services, data: bytes, file_name: str, *, rebuild: bool = False) -> dict:
    settings = services.settings
    check_pdf(data, file_name, settings.max_upload_mb)
    upload = settings.data_dir / "uploads" / f"{sha256_bytes(data)}.pdf"
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(data)

    artifact = None if rebuild else load_artifact(settings, doc_id_from_filename(file_name))
    reused = artifact is not None and artifact["sha256"] == sha256_bytes(data)
    if not reused:
        artifact = await build_artifact(data, file_name, services.llm, settings)
        save_artifact(settings, artifact)
    index_report = await index_artifact(artifact, services.store, services.embedder)
    services.registry.upsert_document(artifact, points=index_report["points"])
    log.info("ingested doc=%s reused_artifact=%s points=%d", artifact["doc_id"], reused, index_report["points"])
    return {
        "doc_id": artifact["doc_id"],
        "title": artifact["title"],
        "reused_artifact": reused,
        "extraction": artifact["report"],
        "index": index_report,
    }
