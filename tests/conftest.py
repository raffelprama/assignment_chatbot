"""Test doubles: a scripted LLM, a deterministic embedder and an in-memory Qdrant. No network."""

import hashlib
import math
from pathlib import Path

import pytest

from app.config import Settings
from app.errors import ServiceUnavailable
from app.knowledge import KnowledgeCatalog
from app.llm.factory import StructuredResult
from app.llm.usage import Usage
from app.registry import Registry
from app.retrieval.sparse import tokenize
from app.retrieval.store import VectorStore, make_client
from app.services import Services

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "data" / "kb"
EXTRACTED_DIR = ROOT / "data" / "extracted"


class FakeEmbedder:
    """Bag-of-words hashing vectors: similar wording -> similar vectors, fully deterministic."""

    dim = 64

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in tokenize(text):
            vec[int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class ScriptedLLM:
    """Returns canned schema objects per node; a node mapped to an exception raises it."""

    def __init__(self, script: dict):
        self.script = script
        self.calls: list[str] = []

    async def structured(self, schema, messages, *, node: str, model: str) -> StructuredResult:
        self.calls.append(node)
        item = self.script[node]
        if isinstance(item, Exception):
            raise item
        value = item(messages) if callable(item) else item
        return StructuredResult(value=schema.model_validate(value),
                                usage=Usage(node=node, model="fake", input_tokens=10, output_tokens=5))


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(API_KEY="test-key", qdrant_local_path=":memory:", collection="test_kb",
                    data_dir=tmp_path, embedding_dim=FakeEmbedder.dim, judge_enabled=True)


@pytest.fixture
def make_services(settings):
    def factory(script: dict) -> Services:
        return Services(
            settings=settings,
            llm=ScriptedLLM(script),
            embedder=FakeEmbedder(),
            store=VectorStore(make_client(settings), settings.collection),
            registry=Registry(settings.data_dir / "registry.sqlite"),
            catalog=KnowledgeCatalog(EXTRACTED_DIR),
        )
    return factory


UNAVAILABLE = ServiceUnavailable("simulated outage")
