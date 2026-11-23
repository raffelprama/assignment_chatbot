"""Persistent embedding cache (SQLite). Re-ingesting or re-running the evaluation costs no quota."""

import hashlib
import json
import sqlite3
import threading
from pathlib import Path


class EmbeddingCache:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, vec TEXT)")
            self._conn.commit()

    @staticmethod
    def key(model: str, dim: int, task: str, text: str) -> str:
        return hashlib.sha256(f"{model}|{dim}|{task}|{text}".encode("utf-8")).hexdigest()

    def get_many(self, keys: list[str]) -> dict[str, list[float]]:
        if not keys:
            return {}
        with self._lock:
            found = {}
            for start in range(0, len(keys), 500):
                chunk = keys[start:start + 500]
                marks = ",".join("?" * len(chunk))
                rows = self._conn.execute(f"SELECT key, vec FROM emb WHERE key IN ({marks})", chunk).fetchall()
                found.update({k: json.loads(v) for k, v in rows})
            return found

    def put_many(self, items: dict[str, list[float]]) -> None:
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO emb VALUES (?, ?)", [(k, json.dumps(v)) for k, v in items.items()]
            )
            self._conn.commit()
