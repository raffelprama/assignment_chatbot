"""Runtime configuration, read from environment variables and `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Credentials (names match the provided .env)
    gemini_api_key: SecretStr = Field(validation_alias="API_KEY")
    qdrant_api_key: SecretStr | None = Field(default=None, validation_alias="QDRANT_API_KEY")
    qdrant_cluster: str | None = Field(default=None, validation_alias="QDRANT_CLUSTER")
    # Set QDRANT_LOCAL_PATH to run Qdrant embedded (no server); ":memory:" for tests.
    qdrant_local_path: str | None = None
    collection: str = "sop_kb"

    # Models (probed 2026-11-23 on the free tier):
    # - gemini-3.5-flash-lite: ~1.5 s per call, no thinking tokens, correct structured output -> primary.
    # - gemini-2.5-flash: free-tier quota is 20 requests/day per model; exhausted during development.
    # - gemini-3.6-flash works but ~17 s; gemini-3.1-flash-lite returned 503 (overloaded);
    #   gemini-2.5-flash-lite returned "model not found" for this key.
    # Fallbacks are tried in order on any failure; the whole chain is retried after a backoff.
    model_answer: str = "gemini-3.5-flash-lite"
    model_fast: str = "gemini-3.5-flash-lite"
    model_fallbacks: list[str] = ["gemini-3.6-flash", "gemini-3.1-flash-lite"]
    llm_chain_rounds: int = 3
    llm_backoff_s: float = 3.0
    # A quota error asking for a longer wait than this marks the model exhausted for that long
    # (a daily quota said "retry in 59827s"); the chain skips it instead of sleeping.
    max_retry_wait_s: float = 45.0
    # Free-tier quotas (observed: 100 embedding requests/min, each batched text counts as one).
    embed_rpm: int = 90
    llm_rpm: int = 30
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    llm_timeout_s: int = 60
    llm_max_retries: int = 2

    # Retrieval and answering
    top_k: int = 3
    top_k_wide: int = 8
    retrieval_pool: int = 20
    rrf_k: int = 60
    max_question_chars: int = 1000
    judge_enabled: bool = True

    # Ingestion
    min_text_chars_per_page: int = 40
    vision_render_dpi: int = 200
    max_upload_mb: int = 15
    keys_per_section: int = 5

    # Optional API key for the HTTP API (empty = open, fine for a local PoC)
    service_api_key: SecretStr | None = None

    data_dir: Path = DATA_DIR

    @property
    def qdrant_url(self) -> str | None:
        if not self.qdrant_cluster:
            return None
        cluster = self.qdrant_cluster.strip()
        return cluster if cluster.startswith("http") else f"https://{cluster}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
