# Retrieval evaluation (no LLM)

Questions with expected sections: 32. Normalized queries come from run `baseline`.

| Configuration | Hit@3 | Recall@3 | Recall@5 | Recall@8 | Questions not fully covered at k=3 |
|---|---|---|---|---|---|
| hybrid · all units · normalized query | 1.00 | 0.93 | 0.95 | 0.97 | H3, H4, H6, M1 |
| dense only · all units · normalized query | 1.00 | 0.93 | 0.93 | 0.97 | H3, H4, H6, M1 |
| BM25 only · all units · normalized query | 1.00 | 0.95 | 0.95 | 0.97 | H3, H4, M1 |
| hybrid · sections only (no question keys / doc maps) | 0.97 | 0.92 | 0.94 | 0.94 | H3, H4, L2, M1 |
| hybrid · sections + doc maps (no question keys) | 1.00 | 0.93 | 0.97 | 0.97 | H3, H4, H6, M1 |
| hybrid · all units · raw user question | 1.00 | 0.93 | 0.96 | 0.97 | H3, H4, H6, M1 |

Hit@k = at least one expected section in the top k. Recall@k = share of expected sections in the top k (multi-section questions need all of them).
