"""PDF -> validated artefact (pages, sections, doc map, question keys).

The artefact is the single source for indexing. It is written to `data/extracted/<doc_id>.json`
so the index can be rebuilt without repeating vision and key-generation calls.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.errors import ExtractionError
from app.ids import doc_id_from_filename, doc_label, sha256_bytes
from app.ingestion.extract import extract_pages
from app.ingestion.keys import generate_keys
from app.ingestion.structure import ParsedDocument, parse_document, validate
from app.llm.factory import LLM
from app.llm.usage import summarize

log = logging.getLogger(__name__)


def doc_map_text(doc: ParsedDocument) -> str:
    """Deterministic overview of a document, so "what does this SOP cover?" has an answer source."""
    items = "; ".join(
        f"§{s.section_no} {s.title}" if s.section_no is not None else s.title for s in doc.sections
    )
    return f"{doc.title}. Isi dokumen ({len(doc.sections)} bagian): {items}."


def artifact_path(settings: Settings, doc_id: str) -> Path:
    return settings.data_dir / "extracted" / f"{doc_id}.json"


async def build_artifact(
    pdf_bytes: bytes, file_name: str, llm: LLM, settings: Settings, *, with_keys: bool = True
) -> dict:
    doc_id = doc_id_from_filename(file_name)
    pages, usages = await extract_pages(pdf_bytes, llm, settings)
    doc = parse_document(pages, fallback_title=doc_id)
    problems = validate(doc)
    if problems:
        raise ExtractionError(f"Extraction of '{file_name}' failed validation", detail=problems)

    keys, key_counts = {}, {"kept": 0, "dropped": 0}
    if with_keys:
        keys, key_counts, key_usage = await generate_keys(doc, llm, settings)
        if key_usage:
            usages.append(key_usage)

    artifact = {
        "doc_id": doc_id,
        "label": doc_label(doc_id),
        "file_name": file_name,
        "sha256": sha256_bytes(pdf_bytes),
        "title": doc.title,
        "structure": doc.structure,
        "pages": [p.to_dict() for p in pages],
        "sections": [s.to_dict() for s in doc.sections],
        "doc_map": doc_map_text(doc),
        "keys": {str(no): items for no, items in keys.items()},
        "report": {
            "pages_by_method": _count(p.method for p in pages),
            "layouts": _count(p.layout for p in pages),
            "sections": len(doc.sections),
            "keys": key_counts,
            "validator": problems,
            "usage": summarize(usages),
        },
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    log.info("artifact_built doc=%s sections=%d keys=%s", doc_id, len(doc.sections), key_counts)
    return artifact


def save_artifact(settings: Settings, artifact: dict) -> Path:
    path = artifact_path(settings, artifact["doc_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_artifact(settings: Settings, doc_id: str) -> dict | None:
    path = artifact_path(settings, doc_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _count(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
