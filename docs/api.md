# API reference

Base path `/api/v1`. Interactive docs at `http://127.0.0.1:8000/docs` when the server runs;
machine-readable spec in [`openapi.json`](openapi.json).

Every error has one shape:

```json
{"error": "NotFound", "message": "Document 'nope' not found", "detail": null, "trace_id": "9a33511d4e7e"}
```

| Status | When |
|---|---|
| 200 | Chat always returns 200 for a domain outcome — see `status` below |
| 202 | Upload / re-index accepted; poll the job |
| 400 / 413 / 415 | Bad file: empty, larger than 15 MB, not a PDF |
| 401 | `SERVICE_API_KEY` is set and `X-API-Key` is missing or wrong |
| 404 | Unknown document, job or question key |
| 422 | Request validation failed |
| 503 | A dependency failed (LLM, embeddings, Qdrant). Never disguised as "no answer" |

If `SERVICE_API_KEY` is set, every `/api/v1/*` call needs the header `X-API-Key`.

## Chat

### `POST /api/v1/main/chat`

```json
{"question": "Berapa target respons awal untuk tiket P1?", "top_k": 3}
```

`question`: 1–1000 characters. `top_k`: optional, 1–10 (default 3).

Response (abridged, real output):

```json
{
  "status": "answered",
  "answer": "Target respons awal untuk tiket P1 adalah 15 menit [KB_01 §4]. ...",
  "citations": [{
    "evidence_id": "KB_01 §4", "doc_title": "Penanganan Tiket Layanan",
    "file_name": "KB_01_Penanganan_Tiket_Layanan.pdf", "pages": [1],
    "section_no": 4, "section_title": "Target Respons Awal",
    "quote": "P1: 15 menit; P2: 1 jam; P3: 4 jam kerja; P4: 1 hari kerja."
  }],
  "missing": null,
  "language": "id", "intent": "in_scope", "search_query": "target respons awal prioritas tiket P1",
  "judge": "pass",
  "retrieved": [{"evidence_id": "KB_01 §4", "score": 0.0328, "dense_rank": 1, "sparse_rank": 1,
                 "best_dense_score": 0.84, "matched_via": ["qkey", "section"]}],
  "route": ["normalize", "retrieve", "answer", "check_citations", "judge", "respond"],
  "usage": {"llm_calls": 3, "input_tokens": 1875, "output_tokens": 210, "cost_usd": 0.0011, "models": ["gemini-3.5-flash-lite"]},
  "timings_ms": {"normalize": 1700, "retrieve": 380, "answer": 2100, "judge": 1600, "total": 5800}
}
```

| `status` | Meaning |
|---|---|
| `answered` | Fully answered from the documents; every factual sentence is cited |
| `partial` | Part is answered and cited; `missing` says what the documents do not specify |
| `no_answer` | Nothing in the documents answers it (fixed template, no citations) |
| `out_of_scope` | Clearly unrelated to the documents (fixed template) |
| `unsafe` | Prompt-extraction / rule-override / harmful request (fixed template) |

`judge` is `pass`, `incomplete`, `unsupported`, `irrelevant`, `unavailable` (judge call failed, the
answer was still citation-checked) or `skipped` (refusals and `no_answer` are not judged).

## Documents

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/rag/documents` | Upload a PDF (multipart field `file`) → `202 {job_id, doc_id}`. Runs extraction, key generation, indexing and the smoke test in the background |
| `GET` | `/api/v1/rag/jobs/{job_id}` | `processing` / `completed` / `failed`, with the report (pages by method, layouts, sections, keys, points by kind, smoke-test failures, tokens, cost) or the error |
| `GET` | `/api/v1/rag/documents` | Indexed documents with status, section and point counts |
| `GET` | `/api/v1/rag/documents/{doc_id}` | Pages (extraction method, layout, routing reason), verbatim sections, doc map, report |
| `POST` | `/api/v1/rag/documents/{doc_id}/reindex?rebuild=false` | Re-index from the stored PDF/artefact; `rebuild=true` re-runs extraction and keys |
| `DELETE` | `/api/v1/rag/documents/{doc_id}` | Delete the document's points, artefact and registry entry → `204` |

```bash
curl -F "file=@data/kb/KB_02_Pengelolaan_Keluhan_Pelanggan.pdf" http://127.0.0.1:8000/api/v1/rag/documents
curl http://127.0.0.1:8000/api/v1/rag/jobs/<job_id>
```

## Question keys (the "Q" of Q/A indexing)

Keys are alternative phrasings that point at a section. Adding one is how an operator fixes "this
wording did not find the right section" without editing the source document.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/rag/keys?doc_id=...&section_no=3` | List keys of a document (optionally one section) |
| `POST` | `/api/v1/rag/keys` | `{"doc_id", "section_no", "text", "lang"}` → embedded and searchable immediately (`201`) |
| `DELETE` | `/api/v1/rag/keys/{key_id}` | Remove a key (`204`; `404` if unknown) |

## Search (no LLM)

`POST /api/v1/rag/search` `{"query": "eskalasi SEV2", "top_k": 5, "mode": "hybrid" | "dense" | "sparse"}`
returns the ranked units with fused score, per-channel ranks and which point kinds matched.

## Health

`GET /health` → liveness. `GET /ready` → 200 with collection, point count, documents and models when
the index is populated; 503 when Qdrant is unreachable or the collection is empty.
