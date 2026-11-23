"""Document and job registry (SQLite). Qdrant holds vectors; job state is not vector data."""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY, label TEXT, file_name TEXT, title TEXT, sha256 TEXT,
    status TEXT, sections INTEGER, points INTEGER, report TEXT, created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY, doc_id TEXT, file_name TEXT, status TEXT, error TEXT,
    report TEXT, created_at TEXT, updated_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registry:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)

    def _execute(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            self._conn.commit()
            return rows

    # documents
    def upsert_document(self, artifact: dict, *, points: int, status: str = "indexed") -> None:
        now = _now()
        self._execute(
            """INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(doc_id) DO UPDATE SET label=excluded.label, file_name=excluded.file_name,
               title=excluded.title, sha256=excluded.sha256, status=excluded.status,
               sections=excluded.sections, points=excluded.points, report=excluded.report,
               updated_at=excluded.updated_at""",
            (artifact["doc_id"], artifact["label"], artifact["file_name"], artifact["title"],
             artifact["sha256"], status, len(artifact["sections"]), points,
             json.dumps(artifact["report"], ensure_ascii=False), now, now),
        )

    def list_documents(self) -> list[dict]:
        return [self._doc(row) for row in self._execute("SELECT * FROM documents ORDER BY doc_id")]

    def get_document(self, doc_id: str) -> dict | None:
        rows = self._execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,))
        return self._doc(rows[0]) if rows else None

    def delete_document(self, doc_id: str) -> None:
        self._execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))

    # jobs
    def create_job(self, job_id: str, doc_id: str, file_name: str) -> None:
        now = _now()
        self._execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                      (job_id, doc_id, file_name, "processing", None, None, now, now))

    def finish_job(self, job_id: str, *, status: str, report: dict | None = None, error: str | None = None) -> None:
        self._execute("UPDATE jobs SET status=?, report=?, error=?, updated_at=? WHERE job_id=?",
                      (status, json.dumps(report, ensure_ascii=False) if report else None, error, _now(), job_id))

    def get_job(self, job_id: str) -> dict | None:
        rows = self._execute("SELECT * FROM jobs WHERE job_id=?", (job_id,))
        if not rows:
            return None
        job = dict(rows[0])
        job["report"] = json.loads(job["report"]) if job["report"] else None
        return job

    @staticmethod
    def _doc(row: sqlite3.Row) -> dict:
        doc = dict(row)
        doc["report"] = json.loads(doc["report"]) if doc["report"] else None
        return doc
