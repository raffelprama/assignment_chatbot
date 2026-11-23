# Architecture

Two paths share one Qdrant collection: **ingestion** turns PDFs into verified, citable units;
**question answering** retrieves those units and only shows answers whose citations check out.

## 1. Ingestion

```
PDF ──► per-page routing (app/ingestion/extract.py)
          │ text layer passes quality check ─► column-aware text extraction (text-run coordinates)
          │ no / unreadable text layer ──────► page image ─► vision LLM, verbatim transcription
          ▼
        structure parse (app/ingestion/structure.py)
          numbered headings "N. Title" (sequence-checked) → one section each
          no numbered headings → paragraph windows (fallback)
          validator: sections non-empty, no other section's heading inside a body (column splice)
          ▼
        artefact data/extracted/<doc>.json (app/ingestion/pipeline.py)
          pages + method/layout, sections (verbatim), doc map, question keys, report (tokens, cost)
          ▼
        index (app/ingestion/indexer.py) ─► Qdrant: dense (Gemini embedding) + BM25 sparse per point
          point kinds:  section (verbatim text) · qkey (question → section) · docmap (document overview)
          ids = uuid5(file sha256, kind, section, key index) → idempotent, versioned
          write new version → smoke test (each section title retrieves its section) → delete old versions
```

**Routing per page, on quality.** A page uses its text layer only if it has enough characters,
no `(cid:N)` glyph ids and a plausible letter ratio. Otherwise it goes to the vision model. In
this corpus KB_01 and KB_04 are image-only (≈122 dpi raster pages) and KB_02/KB_03 have text layers.

**Two columns.** Text runs carry x/y coordinates. A second column is detected when several runs
start in the middle band of the page and share baselines with the left side; the reader then
emits the header, the whole left column, then the right column. KB_03 shows why this matters: a
plain top-to-bottom reader interleaves §1 with §7 line by line, and the validator catches it
(`eval/reports/extraction.md`). For scans, the vision prompt asks for column-by-column order.

**Q/A indexing without paraphrased answers.** For each section the LLM writes 5 question keys
(formal Indonesian, colloquial, keyword-style, English). Keys only *point at* a section; the answer
evidence is always the verbatim section text. Keys are constrained to questions the section fully
answers, and Indonesian keys must share a content word with their section.

**Document map.** One deterministic point per document lists its title and section titles, so
"which SOPs exist / what does this SOP cover" has a citable source.

## 2. Question answering (LangGraph, `app/graph/build.py`)

```
POST /api/v1/main/chat
   │
normalize   1 LLM call, sees a scope card (document + section titles)
   │          → intent (in_scope | catalog | off_domain | unsafe), Indonesian search query, answer language
   │          off_domain / unsafe ─────────────────────────────────────────────────────► respond (template)
   ▼
retrieve    dense(search query) + BM25(search query + original wording)
   │          reciprocal rank fusion → hits on sections/keys/doc maps collapsed to citable units → top_k
   │          catalog intent → every document map
   ▼
answer      1 LLM call; evidence = verbatim units in <evidence id="KB_01 §4"> tags (data, not instructions)
   │          → status answered | partial | no_answer, answer with inline [ids], citations{id, verbatim quote}, missing
   ▼
check_citations   deterministic: cited unit was retrieved AND quote is a substring of it
   │          invalid citations dropped, unknown inline markers removed, no valid citation ⇒ no_answer
   ▼
judge       1 LLM call: supported? complete? relevant?
   │          pass ─────────────────────────────────────────────────────────────────────► respond
   │          incomplete / irrelevant (once) → widen top_k to 8 → retrieve again
   │          unsupported (once) → regenerate with the reviewer's list of unsupported claims
   │          still failing → incomplete becomes partial; unsupported becomes "could not verify"
   ▼
respond     templates for out_of_scope / unsafe / no_answer; otherwise the checked answer
```

Typical turn: 3 LLM calls (normalize, answer, judge) and 1 embedding call. Worst case: 5 LLM calls.

### Failure policy

| Component fails | What the user gets | Why |
|---|---|---|
| normalize LLM | turn continues as in-scope with the raw question | later layers still protect; refusing everything during an outage is wrong too |
| embeddings / Qdrant | HTTP 503 | a broken dependency is never disguised as "not found" |
| answer LLM | HTTP 503 | no answer without a model |
| citation check | cannot fail open: no valid citation ⇒ `no_answer` | the deterministic safety layer |
| judge LLM | the answer, flagged `judge: unavailable` (citations were already verified) | the judge is a second opinion |

All LLM calls go through `app/llm/factory.py`: schema-validated structured output, a fallback model
chain, a requests-per-minute limiter, and retry that honours the provider's "retry in N s" hint. A
model whose quota is exhausted for longer than `MAX_RETRY_WAIT_S` is skipped instead of waited on.

## 3. Data and state

| What | Where | Committed |
|---|---|---|
| Source PDFs | `data/kb/` | yes |
| Extraction artefacts (pages, sections, keys, report) | `data/extracted/*.json` | yes — re-indexing needs no vision or key-generation calls |
| Vectors + payloads | Qdrant collection `sop_kb` | no (rebuilt by `python -m app.ingest`) |
| Documents and jobs | `data/registry.sqlite` | no |
| Embedding cache | `data/cache/embeddings.sqlite` | no |
| Uploaded originals | `data/uploads/<sha256>.pdf` | no |

## 4. Code map

| Area | Files |
|---|---|
| Config, errors, ids, prices | `app/config.py`, `app/errors.py`, `app/ids.py`, `app/pricing.py` |
| LLM access, usage, limits, cache, prompts | `app/llm/` |
| Ingestion | `app/ingestion/{extract,structure,keys,pipeline,indexer,service}.py`, CLI `app/ingest.py` |
| Retrieval | `app/retrieval/{store,sparse,hybrid}.py` |
| Chat graph | `app/graph/{build,state,schemas,citations,templates}.py`, entry `app/chat.py`, CLI `app/ask.py` |
| HTTP API | `app/main.py`, `app/api/`, `app/schemas.py` |
| Evaluation | `eval/run.py`, `eval/retrieval_eval.py`, `eval/extraction_eval.py`, `eval/questions*.jsonl` |
| Tests | `tests/` (no network: scripted LLM, hashing embedder, in-memory Qdrant) |

## 5. Library calls checked against the installed versions

Signatures were read from the installed packages before use (2026-11-23): `ChatGoogleGenerativeAI`
(`with_structured_output(method="json_schema", include_raw=True)`), `GoogleGenerativeAIEmbeddings`
(`task_type`, `output_dimensionality`), qdrant-client 1.20 (`query_batch_points`, `QueryRequest`,
`SparseVectorParams(modifier=IDF)`), LangGraph 1.2 (`StateGraph`, `add_conditional_edges`), pypdf 7
(`extract_text(visitor_text=...)`, `page.images`).
