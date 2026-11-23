# Evaluation

All numbers below come from scripts in `eval/` and raw outputs in `eval/reports/runs/*.jsonl`
(every answer, citation, retrieval rank, token count and timing is stored). Runs were made on
2026-11-23/24 against the Qdrant Cloud collection with the Gemini free tier.

## Summary — what works, what doesn't, what next

**Works**

- **Extraction**: all four PDFs — two image-only scans (one two-column) and two text PDFs (one two-column)
  — produce all 32 sections in the right order. Character error rate 0.0000 against ground truth,
  no numbers lost. The column-aware reader fixes a real interleaving failure (shown below).
- **Answers**: 37/39 (judge on) and 39/39 (judge off) on the main set, 12/12 on a held-out set written
  before prompt tuning. **No hallucinated facts in any run** (no invented retention period, phone number,
  SEV3 rule, or "not required" drawn from silence), across 39 × 3 + 12 answered questions.
- **Traceability**: every shown answer cites file, page, section and a verbatim quote; the deterministic
  check removed 0 citations in the final runs (the model quoted correctly), and the tests prove it
  rejects fabricated quotes.
- **Honest partial answers** for half-covered questions (retention period, compensation amount, SEV3/SEV4
  rules, internal vs customer update intervals) and clean refusals for off-domain and prompt-extraction requests.

**Fails / inaccurate**

- **Run-to-run variability** on 2 of 39 questions. `gemini-3.5-flash-lite` uses fixed sampling (ignores
  `temperature=0`), so "Apakah P1 sama dengan SEV1?" was once answered `no_answer` (safe but unhelpful) and
  once correctly as `partial`; "P1 masuk pukul 10.00, kapan paling lambat?" once omitted the computed 10.15.
- **Latency** is dominated by the free-tier provider: p50 6.6–16.8 s, p95 51–98 s across runs, because of
  503 overload errors and fallback to a slower model. Without overload the three calls take ~6 s total.
- **The LLM judge showed no measurable benefit** on this corpus: in the v2 run it passed or skipped every
  answer (never changed an outcome), while adding ~45 % LLM calls and latency.
- **Hybrid retrieval and question keys showed no measurable benefit** on this corpus (all retrieval
  configurations within one question of each other). Their value on larger corpora is plausible but unproven here.

**Priorities with more time**

1. **Stability**: run each question ≥ 3 times and report flip rates; pick a model that honours
   `temperature=0` (or pass a fixed seed) for the answer step.
2. **Decide the judge on evidence**: with the citation check already guaranteeing traceability, make the
   judge opt-in, or restrict it to `partial`/multi-section answers where completeness matters.
3. **Finish the ablations that were cut** (whole-KB-in-prompt, top_k 5/8, stability): commands below.
4. **A harder corpus** (multi-page, tables, mixed scan/text pages, more vocabulary mismatch) — the
   current one is too small to separate retrieval strategies.
5. **Latency**: a paid tier or a provider with SLAs; run normalize in parallel with a speculative
   retrieval on the raw question.

## 1. Extraction (`python -m eval.extraction_eval` → `eval/reports/extraction.md`)

| Check | Result |
|---|---|
| Vision path forced on KB_02 and KB_03, compared with their real text layers | CER 0.0000 and 0.0000; no numbers missing; 8/8 sections each; validator clean |
| KB_01 and KB_04 (image-only, ≈122 dpi) vision transcription vs hand transcription | CER 0.0000 and 0.0000; no numbers missing; 8/8 sections; validator clean |
| KB_03 (two columns) read by a naive top-to-bottom reader | sections 1–6 only; §1 starts with "7. Pelaporan Mingguan Layanan reguler…" (columns interleaved); validator flags the splice |
| KB_03 read by the column-aware reader | sections 1–8, correct order |

The hand transcriptions in `eval/gold/` were typed from the page images; a second person should spot-check them.

## 2. Retrieval (`python -m eval.retrieval_eval` → `eval/reports/retrieval.md`, no LLM calls)

32 questions with known source sections; normalized queries replayed from the `baseline` run.

| Configuration | Hit@3 | Recall@3 | Recall@5 | Recall@8 |
|---|---|---|---|---|
| **hybrid, all units (production)** | 1.00 | 0.93 | 0.95 | 0.97 |
| dense only | 1.00 | 0.93 | 0.93 | 0.97 |
| BM25 only | 1.00 | 0.95 | 0.95 | 0.97 |
| sections only (no question keys / doc maps) | 0.97 | 0.92 | 0.94 | 0.94 |
| sections + doc maps (no question keys) | 1.00 | 0.93 | 0.97 | 0.97 |
| raw user question instead of the normalized query | 1.00 | 0.93 | 0.96 | 0.97 |

Reading: one question ≈ 0.03. Every configuration is within one question of the others, so **no channel or
unit type is shown to matter on this corpus**. What does matter is **k**: the questions not fully covered at
k = 3 are exactly the multi-section ones (M1 data-leak needs 5 sections; H3, H4, H6 need two documents).
The answer step still handled them (as `answered`/`partial`) because the most important sections ranked first.

## 3. End to end (`python -m eval.run`)

39 questions (`eval/questions.jsonl`): 11 direct, 2 document-overview, 4 multi-section, 8 ambiguous,
8 unsupported/off-domain, 6 adversarial (prompt injection, false premise, prompt extraction,
outside-knowledge request, cross-lingual, arithmetic). Each question lists acceptable statuses, required
facts, forbidden content (e.g. any number of years for the retention question; "tidak wajib" for SEV3
review) and the expected source sections.

| Run | Prompts | Judge | Correct | Hallucinations | Errors (1st pass) | p50 / p95 s | LLM calls / q | Cost / q (paid tier) |
|---|---|---|---|---|---|---|---|---|
| `baseline` | initial | on | 33/39 | 0 | 3 (provider 503) | 11.0 / 92.4 | 2.61 | $0.0010 |
| `v2` | revised | on | 37/39 | 0 | 0 | 16.8 / 98.3 | 2.69 | $0.0010 |
| `no_judge` | revised | off | **39/39** | 0 | 0 | 6.6 / 51.2 | 1.85 | $0.0009 |
| `heldout_v2` (12 new questions) | revised | on | **12/12** | 0 | 0 | — | — | — |

By group (`v2`): direct 11/11 · overview 2/2 · multi-section 4/4 · ambiguous 7/8 · unsupported 8/8 · adversarial 5/6.

**What changed between `baseline` and `v2`** (each change targets a failure class, not a question):

| Baseline failure | Cause found in the trace | Change |
|---|---|---|
| U6 "cara mereset kata sandi pelanggan" refused as off-domain | normalize judged it unrelated; retrieval never ran | normalize: subjects the documents deal with (accounts, passwords, verification…) stay in scope even if the exact procedure may be missing |
| H4 "Apakah P1 sama dengan SEV1?" → `no_answer` | query compressed to "P1 SEV1" lost the ticket-priority section; answer chose `no_answer` | normalize writes descriptive queries ("prioritas tiket P1", "tingkat insiden SEV1"); answer uses `partial` whenever any subject is defined |
| H2 SEV1 customer-update interval: omitted the related 20-minute internal rule | — | answer: mention closely related values for a different audience, labelled as such |
| A3, H1, X6: provider 503 | free-tier overload | eval re-tries errored questions once and reports first-pass errors |

**Guarding against overfitting**: the 12 held-out questions (`eval/questions_heldout.jsonl`) were written and
frozen *before* the v2 changes. They probe the same failure classes on different content ("Is P2 the same as
SEV2?", "Bagaimana cara mengubah email akun pelanggan?", "SEV2 internal update?") — 12/12.

**Instrument errors found and fixed** (validate the ruler before trusting it): two runs reported a
"hallucination" that was the correct answer — the forbidden pattern `p1 sama dengan sev1` matched "Dokumen
**tidak menyatakan bahwa** P1 sama dengan SEV1", and `p2 is the same as sev2` matched "do not state
**whether** P2 is the same as SEV2". The checker now ignores matches preceded by a negation cue in the same
sentence (`_affirmative_match` in `eval/run.py`, sanity-tested to still catch affirmative claims), and all
runs were re-scored from their stored outputs. Known leniency: an affirmative claim after an unrelated
negation in the same sentence would be missed; every "correct" answer in the reports can be read in full in
the `.md` files.

## 4. The judge

In `v2` the judge returned `pass` 32 times and was skipped 7 times (refusals and `no_answer`); it never
triggered a retry or changed an outcome. Turning it off (`no_judge`) cut LLM calls per question from 2.69 to
1.85 and latency by more than half (partly provider variance), with no loss in correctness. The two questions
that differ between `v2` and `no_judge` (H4, X6) differ because of answer-step sampling, not the judge.
Conclusion for this corpus: **the deterministic citation check carries the safety load; the judge has not
earned its cost**. It stays on by default because the requested pipeline is normalize → answer → judge,
and can be disabled with `JUDGE_ENABLED=false`. Its retry paths are covered by tests (`tests/test_graph.py`).

## 5. Cost and latency

| Item | Tokens | Cost at paid-tier list prices |
|---|---|---|
| Ingestion of all 4 PDFs (2 vision pages + 4 question-key calls, `gemini-2.5-flash`) | 3.4k in / 13.8k out | ≈ $0.036 (2.5-flash price unverified) |
| One question, judge on (`v2` mean) | 1.8k in / 0.25k out, 2.7 calls | ≈ $0.0010 |
| One question, judge off (`no_judge` mean) | 1.3k in / 0.19k out, 1.9 calls | ≈ $0.0009 |
| Embeddings | 196 index texts + ~1 per question | not metered by the SDK; ≈ $0 at this size |

Prices: `app/pricing.py` (read 2026-11-23 from the official pricing page; `gemini-3.5-flash-lite` verbatim,
others from a summary of a truncated page — marked `verified=False`). **On the free tier all of this is $0.**

Per-node median latency in `v2`: normalize 3.3 s · retrieve 0.9 s · answer 4.0 s · judge 3.7 s. Earlier in the
day the same nodes took 1.7 / 0.4 / 2.1 / 1.6 s; the spread is provider load. Fallbacks used in the runs:
`gemini-3.6-flash` (~17 s per call) and `gemini-3.1-flash-lite`.

## 6. Experiments not completed

| Experiment | Status | Command to run it |
|---|---|---|
| Whole knowledge base in the prompt instead of retrieval | **stopped after 9 of 39 questions** (8 correct, 1 rate-limit error): the host machine ran low on memory and the run was killed; it was also hitting per-minute rate limits because each prompt carries all 32 sections | `python -m eval.run --name full_context --full-context` |
| top_k = 5 on the 12 multi-section/ambiguous questions | not run (same stop) | `python -m eval.run --name top5 --top-k 5 --ids M1,M2,M3,M4,H1,H2,H3,H4,H5,H6,A11,L2` |
| Stability (10 questions × 2 extra runs) | not run (same stop) | `python -m eval.run --name stab_r2 --ids A1,A9,M1,H1,H2,H4,U1,U8,X2,X6` |

## 7. Limits of this evaluation

- 51 questions, written by one person from the same PDFs the system indexes; expected outcomes for
  "the SOP is silent" cases are interpretations of absence.
- Checks are keyword/regex based; they verify required facts and forbidden content, not fluency. All answers
  are in `eval/reports/*.md` for human reading.
- One run per configuration (except the held-out set, which is itself a single run); with fixed-sampling
  models, a single question can flip between runs.
- The corpus (4 pages, 32 sections) cannot separate retrieval strategies; results say nothing about scale.
