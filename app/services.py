"""Long-lived clients, built once (FastAPI lifespan or a CLI run) and shared."""

from dataclasses import dataclass

from app.config import Settings
from app.knowledge import KnowledgeCatalog
from app.llm.factory import LLM, Embedder
from app.registry import Registry
from app.retrieval.store import VectorStore, make_client


@dataclass
class Services:
    settings: Settings
    llm: LLM
    embedder: Embedder
    store: VectorStore
    registry: Registry
    catalog: KnowledgeCatalog
    graph: object | None = None  # compiled LangGraph, attached by app.graph.build.attach_graph

    async def close(self) -> None:
        await self.store.close()


def build_services(settings: Settings) -> Services:
    return Services(
        settings=settings,
        llm=LLM(settings),
        embedder=Embedder(settings),
        store=VectorStore(make_client(settings), settings.collection),
        registry=Registry(settings.data_dir / "registry.sqlite"),
        catalog=KnowledgeCatalog(settings.data_dir / "extracted"),
    )
