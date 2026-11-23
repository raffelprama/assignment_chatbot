"""Qdrant access: one collection, a named dense vector and a named BM25 sparse vector.

Point kinds (payload `kind`): `section` (verbatim section text), `qkey` (a question pointing at a
section) and `docmap` (a document overview). Every point carries its section's text, so a hit on
any kind can be turned into citable evidence without a second lookup.
"""

import logging

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.errors import ServiceUnavailable

log = logging.getLogger(__name__)

DENSE = "dense"
SPARSE = "bm25"


def _describe(exc: Exception) -> str:
    """Short, loggable reason; Qdrant puts the useful part in the message, not the type."""
    return f"{type(exc).__name__}: {' '.join(str(exc).split())[:240]}"


def make_client(settings: Settings) -> AsyncQdrantClient:
    if settings.qdrant_local_path:
        if settings.qdrant_local_path == ":memory:":
            return AsyncQdrantClient(location=":memory:")
        return AsyncQdrantClient(path=settings.qdrant_local_path)
    if not settings.qdrant_url:
        raise ServiceUnavailable("Qdrant is not configured: set QDRANT_CLUSTER or QDRANT_LOCAL_PATH")
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key, timeout=30)


class VectorStore:
    def __init__(self, client: AsyncQdrantClient, collection: str):
        self._client = client
        self.collection = collection

    async def close(self) -> None:
        await self._client.close()

    # Qdrant Cloud runs in strict mode: filtering on an unindexed payload field is a 400 error.
    _PAYLOAD_INDEXES = {
        "doc_id": models.PayloadSchemaType.KEYWORD,
        "kind": models.PayloadSchemaType.KEYWORD,
        "version": models.PayloadSchemaType.KEYWORD,
        "section_no": models.PayloadSchemaType.INTEGER,
    }

    async def ensure_collection(self, dim: int) -> None:
        try:
            if not await self._client.collection_exists(self.collection):
                await self._client.create_collection(
                    self.collection,
                    vectors_config={DENSE: models.VectorParams(size=dim, distance=models.Distance.COSINE)},
                    sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
                )
                log.info("collection_created name=%s dim=%d", self.collection, dim)
            for field, schema in self._PAYLOAD_INDEXES.items():  # idempotent
                await self._client.create_payload_index(self.collection, field, field_schema=schema)
        except Exception as exc:
            raise ServiceUnavailable("Vector store unavailable", detail=_describe(exc)) from exc

    async def upsert(self, points: list[models.PointStruct]) -> None:
        try:
            await self._client.upsert(self.collection, points=points, wait=True)
        except Exception as exc:
            raise ServiceUnavailable("Vector store write failed", detail=_describe(exc)) from exc

    async def delete_doc(self, doc_id: str, *, keep_version: str | None = None) -> None:
        """Delete a document's points; with `keep_version`, only older versions (write-then-swap)."""
        must_not = [] if keep_version is None else [
            models.FieldCondition(key="version", match=models.MatchValue(value=keep_version))
        ]
        selector = models.FilterSelector(filter=models.Filter(
            must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))],
            must_not=must_not,
        ))
        try:
            await self._client.delete(self.collection, points_selector=selector, wait=True)
        except Exception as exc:
            raise ServiceUnavailable("Vector store delete failed", detail=_describe(exc)) from exc

    async def delete_points(self, ids: list[str]) -> None:
        try:
            await self._client.delete(self.collection, points_selector=models.PointIdsList(points=ids), wait=True)
        except Exception as exc:
            raise ServiceUnavailable("Vector store delete failed", detail=_describe(exc)) from exc

    async def scroll(self, conditions: dict[str, str | int]) -> list[models.Record]:
        flt = models.Filter(must=[
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
            for key, value in conditions.items()
        ])
        records: list[models.Record] = []
        offset = None
        try:
            while True:
                batch, offset = await self._client.scroll(
                    self.collection, scroll_filter=flt, limit=256, offset=offset, with_payload=True
                )
                records.extend(batch)
                if offset is None:
                    return records
        except Exception as exc:
            raise ServiceUnavailable("Vector store read failed", detail=_describe(exc)) from exc

    async def query_channels(
        self,
        dense: list[float] | None,
        sparse: tuple[list[int], list[float]] | None,
        limit: int,
        kinds: list[str] | None = None,
    ) -> dict[str, list[models.ScoredPoint]]:
        """Run the dense and/or sparse channel in one round trip; fusion happens in `hybrid.py`."""
        flt = None
        if kinds:
            flt = models.Filter(must=[models.FieldCondition(key="kind", match=models.MatchAny(any=kinds))])
        requests, names = [], []
        if dense is not None:
            requests.append(models.QueryRequest(
                query=dense, using=DENSE, limit=limit, filter=flt, with_payload=True
            ))
            names.append("dense")
        if sparse is not None and sparse[0]:
            requests.append(models.QueryRequest(
                query=models.SparseVector(indices=sparse[0], values=sparse[1]),
                using=SPARSE, limit=limit, filter=flt, with_payload=True,
            ))
            names.append("sparse")
        if not requests:
            return {}
        try:
            responses = await self._client.query_batch_points(self.collection, requests=requests)
        except Exception as exc:
            raise ServiceUnavailable("Vector store query failed", detail=_describe(exc)) from exc
        return {name: response.points for name, response in zip(names, responses)}

    async def get_points(self, ids: list[str]) -> list[models.Record]:
        try:
            return await self._client.retrieve(self.collection, ids=ids, with_payload=True)
        except Exception as exc:
            raise ServiceUnavailable("Vector store read failed", detail=_describe(exc)) from exc

    async def exists(self) -> bool:
        try:
            return await self._client.collection_exists(self.collection)
        except Exception as exc:
            raise ServiceUnavailable("Vector store unavailable", detail=_describe(exc)) from exc

    async def count(self) -> int:
        try:
            return (await self._client.count(self.collection, exact=True)).count
        except Exception as exc:
            raise ServiceUnavailable("Vector store unavailable", detail=_describe(exc)) from exc
