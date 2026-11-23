# SOP Assistant — trustworthy Q&A over operational PDFs

A proof of concept for the *AI Engineer technical assignment*: employees ask questions about SOP
PDFs and get answers that are **relevant**, **traceable to document, page and section**, and
**honest when the documents do not say** — including for scanned and two-column pages.

```
Q: Berapa target respons awal untuk tiket P1?
[answered] Target respons awal untuk tiket P1 adalah 15 menit [KB_01 §4].
  - KB_01_Penanganan_Tiket_Layanan.pdf, page 1, §4 Target Respons Awal: "P1: 15 menit"

Q: Berapa lama data pelanggan disimpan (retensi)?
[partial] Dokumen menyebutkan bahwa salinan lokal harus dihapus sesuai kebijakan retensi [KB_03 §6].
  Not specified in the SOPs: berapa lama data pelanggan disimpan / durasi kebijakan retensi.
```

**Stack:** Python 3.11 · FastAPI · LangGraph + LangChain · Qdrant (dense + BM25 hybrid) · Gemini
(`gemini-3.5-flash-lite` for generation, `gemini-embedding-001` for embeddings).

## Results at a glance

| What | Result | Where |
|---|---|---|
| Extraction of all 4 PDFs (2 scanned, 2 two-column) | 32/32 sections, character error rate **0.0000** on every file, no numbers lost | `eval/reports/extraction.md` |
| Two-column handling | Naive reader interleaves KB_03 columns and loses §7–§8; column-aware reader recovers all 8 (validator catches the splice) | same |
| End-to-end, 39 questions (answerable / ambiguous / unsupported / adversarial) | **37/39 correct with the judge, 39/39 without it — 0 hallucinations in every run** (first run with initial prompts: 33/39) | `eval/reports/v2.md`, `no_judge.md`, `baseline.md` |
| Held-out set written *before* prompt tuning, 12 questions | **12/12**, 0 hallucinations | `eval/reports/heldout_v2.md` |
| Retrieval, 32 questions with known sources | Hit@3 1.00, Recall@3 0.93, Recall@8 0.97 | `eval/reports/retrieval.md` |
| Cost | ≈ $0.001 per question at paid-tier prices (2–3 LLM calls, ~1.8k input / 250 output tokens); **$0 on the free tier** | `docs/evaluation.md` |
| Tests | 25 passing, no network needed | `tests/` |

Full write-up: **[docs/evaluation.md](docs/evaluation.md)** · demo: **[demo/transcript.md](demo/transcript.md)**.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # fill API_KEY (Gemini) and a Qdrant option, see below

python -m app.ingest              # index data/kb/*.pdf  (reuses committed extraction artefacts)
python -m app.ask "Berapa target respons awal untuk tiket P1?"
python -m app.ask "Apakah SEV3 wajib dibuatkan tinjauan pascainsiden?" --json   # full trace

python main.py                    # HTTP API on http://127.0.0.1:8000  (docs at /docs)
curl -X POST http://127.0.0.1:8000/api/v1/main/chat -H "Content-Type: application/json" \
     -d '{"question": "Siapa yang harus dihubungi kalau ada kebocoran data?"}'

pytest                            # 25 tests, no API key or network needed
```

**Qdrant**, pick one: (A) a Qdrant Cloud cluster — `QDRANT_CLUSTER` + `QDRANT_API_KEY` (what this PoC
was evaluated on); (B) no server — `QDRANT_LOCAL_PATH=./qdrant_storage` (embedded Qdrant);
(C) `docker compose up -d` and `QDRANT_CLUSTER=http://localhost:6333`.

**Reproduce the evaluation:** `python -m eval.extraction_eval`, `python -m eval.retrieval_eval`,
`python -m eval.run --name myrun` (39 questions), `python -m eval.run --name ho --questions questions_heldout.jsonl`,
`python -m demo.build_transcript --live`.

## How it works

```
INGEST   PDF ─► route each page ─┬─ usable text layer ─► column-aware text (text-run coordinates)
                                 └─ scan / unreadable ─► page image ─► vision LLM, verbatim
             ─► numbered sections (sequence-checked) ─► validator (fails loudly on column splices)
             ─► artefact data/extracted/<doc>.json ─► Qdrant points:
                  section (verbatim text) · question keys → section · document map
                  each with a dense vector + a BM25 sparse vector

ASK      normalize ─► retrieve ─► answer ─► check citations ─► judge ─► respond
         (scope,       (hybrid     (only from   (quote must be     (supported?   (answered / partial /
          ID query,     RRF,        evidence,    verbatim in a      complete?     no_answer / out_of_scope /
          language)     top 3)      cites)       retrieved section) one retry)    unsafe)
```

Details, failure policy and code map: [docs/architecture.md](docs/architecture.md). API reference:
[docs/api.md](docs/api.md) (`/api/v1/main/chat`, document upload/list/get/re-index/delete, question-key
CRUD, retrieval-only search, health).

## Key technical decisions (full log: [docs/decisions.md](docs/decisions.md))

1. **The answer is always grounded in verbatim section text.** Generated Q/A pairs are used only as
   *retrieval keys* (several phrasings per section, incl. English) — never served as the answer — so a
   number like "15 menit" can always be quoted back to its page.
2. **Citations are checked deterministically before anything is shown**: the cited section must have
   been retrieved and the quote must appear verbatim in it. No valid citation ⇒ no answer. This is the
   one safety layer that cannot fail open.
3. **`partial` is a first-class outcome.** Many SOP questions are half-covered (a retention policy is
   named but has no duration; SEV3 is defined but has no escalation rule). The assistant answers the
   supported part, cites it, and states what the documents do not specify — instead of guessing or
   refusing.
4. **Extraction is routed per page on text quality** and two columns are ordered from text-run
   coordinates; scans go to a vision model. Both were measured, not assumed.
5. **Free-tier engineering**: model fallback chain, rate limiting, retry that honours the provider's
   wait hint, skipping models whose daily quota is exhausted, and an embedding cache.

## Limitations (honest list)

- **Tiny corpus.** 4 one-page documents, 32 sections. Retrieval is near-saturated: hybrid vs dense vs
  BM25 and with/without question keys differ by ≤ 1 question — their benefit is **not demonstrated
  here** (see evaluation). Multi-page PDFs, tables and glyph-id pages are handled by code paths that
  this corpus does not exercise (tables: not specifically handled at all).
- **Evaluation size.** 39 + 12 questions written from my reading of the PDFs; one person's expected
  answers; automatic checks are keyword/regex based (one checker bug was found and fixed — see evaluation).
- **Latency is provider-bound and variable**: ~6 s per question when the model is responsive, but
  p50 6.6–16.8 s and p95 51–98 s across the evaluation runs because of free-tier overload (503) and
  fallback to a slower model.
- **The LLM judge has not earned its cost here.** It never changed an outcome in the evaluated run and adds
  ~45 % LLM calls; the deterministic citation check carries the safety load. It stays on because the
  requested pipeline includes it (`JUDGE_ENABLED=false` turns it off).
- **Run-to-run variability.** `gemini-3.5-flash-lite` ignores `temperature=0`; 2 of 39 questions changed
  outcome between runs ("Apakah P1 sama dengan SEV1?" once `no_answer` instead of the correct `partial`;
  "P1 masuk pukul 10.00…" once without the computed 10.15). Stability runs were not completed.
- **Experiments cut short**: whole-KB-in-the-prompt, top_k 5 and stability runs were stopped when the host
  ran low on memory (commands to finish them are in `docs/evaluation.md` §6).
- **Free-tier quotas.** `gemini-2.5-flash` is limited to 20 requests/day on the key used; the vision
  transcriptions and question keys in `data/extracted/` were produced with it before the quota ran out.
  A full evaluation run is ~110 LLM calls.
- **Single-turn.** No conversation history; follow-up questions must be self-contained.
- **Not production-ready security**: optional single API key, no rate limiting per user, no PII masking.

## Repository map

```
app/            application (ingestion, retrieval, LangGraph chat, FastAPI)
data/kb/        the four SOP PDFs        data/extracted/   committed extraction artefacts
eval/           questions, runners, gold transcriptions, reports/
demo/           transcript.md (the ≥5-question demonstration) and its generator
docs/           architecture, api, decisions, evaluation, openapi.json
tests/          unit + graph tests (offline)
```
