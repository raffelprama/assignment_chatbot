"""Gemini access: structured calls with model fallback, plus cached, rate-limited embeddings.

Fallback is a manual loop (not `Runnable.with_fallbacks`) so every usage record names the model
that actually answered, which the cost report needs. Overload (503/504) and quota (429) errors
were both observed during development, so every call path retries, and quota errors honour the
server's "retry in Ns" hint.
"""

import asyncio
import logging
import time
import warnings
from dataclasses import dataclass
from typing import TypeVar

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from pydantic import BaseModel

from app.config import Settings
from app.errors import ServiceUnavailable
from app.llm.cache import EmbeddingCache
from app.llm.limits import SlidingWindowLimiter, retry_delay_from_error
from app.llm.usage import Usage, usage_from_message

log = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)

# Some models use fixed sampling and warn that `temperature` is ignored; that is expected.
warnings.filterwarnings("ignore", message=".*uses fixed sampling defaults.*")


@dataclass
class StructuredResult:
    value: BaseModel
    usage: Usage


class LLM:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._models: dict[str, ChatGoogleGenerativeAI] = {}
        self._limiter = SlidingWindowLimiter(settings.llm_rpm)
        self._exhausted_until: dict[str, float] = {}

    def _chat_model(self, model: str) -> ChatGoogleGenerativeAI:
        if model not in self._models:
            self._models[model] = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=self._settings.gemini_api_key.get_secret_value(),
                temperature=0,
                timeout=self._settings.llm_timeout_s,
                max_retries=self._settings.llm_max_retries,
            )
        return self._models[model]

    def _candidates(self, primary: str) -> list[str]:
        now = time.monotonic()
        ordered = dict.fromkeys([primary, *self._settings.model_fallbacks])
        return [m for m in ordered if self._exhausted_until.get(m, 0.0) <= now]

    async def structured(
        self, schema: type[SchemaT], messages: list[BaseMessage], *, node: str, model: str
    ) -> StructuredResult:
        """Schema-validated call; on failure try the next model, then retry the chain after a wait."""
        errors: list[str] = []
        wait_s = 0.0
        for round_no in range(self._settings.llm_chain_rounds):
            if round_no:
                await asyncio.sleep(min(max(wait_s, self._settings.llm_backoff_s * round_no),
                                        self._settings.max_retry_wait_s))
            result, wait_s = await self._try_chain(schema, messages, node=node, model=model, errors=errors)
            if result is not None:
                return result
        raise ServiceUnavailable(f"All models failed for step '{node}'", detail=errors)

    async def _try_chain(
        self, schema: type[SchemaT], messages: list[BaseMessage], *, node: str, model: str, errors: list[str]
    ) -> tuple[StructuredResult | None, float]:
        hinted_wait = 0.0
        for candidate in self._candidates(model):
            runnable = self._chat_model(candidate).with_structured_output(schema, include_raw=True)
            await self._limiter.acquire()
            started = time.perf_counter()
            try:
                out = await runnable.ainvoke(messages)
            except Exception as exc:  # provider errors vary by SDK version; record and try the next model
                delay = retry_delay_from_error(exc) or 0.0
                if delay > self._settings.max_retry_wait_s:
                    self._exhausted_until[candidate] = time.monotonic() + delay
                    log.warning("llm_quota_exhausted model=%s retry_in=%.0fs", candidate, delay)
                else:
                    hinted_wait = max(hinted_wait, delay)
                errors.append(f"{candidate}: {type(exc).__name__}: {str(exc)[:160]}")
                log.warning("llm_call_failed node=%s model=%s error=%s", node, candidate, type(exc).__name__)
                continue
            latency_ms = (time.perf_counter() - started) * 1000
            if out.get("parsed") is None:
                errors.append(f"{candidate}: unparseable output ({out.get('parsing_error')})")
                log.warning("llm_parse_failed node=%s model=%s", node, candidate)
                continue
            usage = usage_from_message(out["raw"], node=node, model=candidate, latency_ms=latency_ms)
            return StructuredResult(value=out["parsed"], usage=usage), 0.0
        return None, hinted_wait


class Embedder:
    _ATTEMPTS = 5

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=settings.gemini_api_key.get_secret_value(),
        )
        self._cache = EmbeddingCache(settings.data_dir / "cache" / "embeddings.sqlite")
        self._limiter = SlidingWindowLimiter(settings.embed_rpm)

    @property
    def dim(self) -> int:
        return self._settings.embedding_dim

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        model, dim = self._settings.embedding_model, self.dim
        keys = [EmbeddingCache.key(model, dim, task, text) for text in texts]
        cached = self._cache.get_many(keys)
        missing = [(key, text) for key, text in zip(keys, texts) if key not in cached]
        if missing:
            vectors = await self._call_with_retry([text for _, text in missing], task)
            fresh = {key: vector for (key, _), vector in zip(missing, vectors)}
            self._cache.put_many(fresh)
            cached.update(fresh)
        return [cached[key] for key in keys]

    async def _call_with_retry(self, texts: list[str], task: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        batch_size = max(1, self._settings.embed_rpm // 2)
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            vectors.extend(await self._call_batch(batch, task))
        return vectors

    async def _call_batch(self, batch: list[str], task: str) -> list[list[float]]:
        for attempt in range(self._ATTEMPTS):
            await self._limiter.acquire(len(batch))
            try:
                return await self._client.aembed_documents(
                    batch, task_type=task, output_dimensionality=self.dim
                )
            except Exception as exc:
                if attempt == self._ATTEMPTS - 1:
                    raise ServiceUnavailable(
                        "Embedding service failed", detail=f"{type(exc).__name__}: {str(exc)[:200]}"
                    ) from exc
                delay = retry_delay_from_error(exc) or self._settings.llm_backoff_s * (2 ** attempt)
                if delay > self._settings.max_retry_wait_s:
                    raise ServiceUnavailable(
                        "Embedding quota exhausted", detail=f"provider asks to retry in {delay:.0f}s"
                    ) from exc
                log.warning("embedding_retry attempt=%d delay=%.1fs", attempt + 1, delay)
                await asyncio.sleep(delay + 1.0)
        raise AssertionError("unreachable")
