"""Deterministic identifiers: the same input always yields the same id, on any machine."""

import hashlib
import re
import uuid
from pathlib import Path

_NAMESPACE = uuid.UUID("6f1c2a4e-3b7d-4e8a-9c1f-2d5e7a9b0c11")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def doc_id_from_filename(filename: str) -> str:
    """`KB_01_Penanganan_Tiket_Layanan.pdf` -> `KB_01_Penanganan_Tiket_Layanan`."""
    stem = Path(filename).stem
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", stem).strip("_") or "document"


def doc_label(doc_id: str) -> str:
    """Short citation label: `KB_01` when the id starts with a letters_digits prefix."""
    match = re.match(r"^([A-Za-z]+_\d+)", doc_id)
    return match.group(1) if match else doc_id


def point_id(*parts: object) -> str:
    return str(uuid.uuid5(_NAMESPACE, "|".join(str(p) for p in parts)))
