"""Tokenizer, ids, usage accounting and the deterministic citation check."""

from types import SimpleNamespace

from app.graph.citations import check_citations, strip_unknown_markers
from app.ids import doc_label, point_id
from app.llm.usage import summarize, usage_from_message
from app.retrieval.sparse import query_vector, tokenize

EVIDENCE = [{
    "evidence_id": "KB_01 §4", "doc_id": "KB_01_x", "doc_title": "Penanganan Tiket Layanan",
    "file_name": "KB_01_x.pdf", "pages": [1], "section_no": 4, "section_title": "Target Respons Awal",
    "text": "P1: 15 menit; P2: 1 jam; P3: 4 jam kerja; P4: 1 hari kerja.",
}]


def test_tokenizer_keeps_short_high_signal_tokens():
    tokens = tokenize("Berapa target respons tiket P1 dan SEV2? Jangan minta OTP/PIN ke PIC.")
    for expected in ("p1", "sev2", "otp", "pin", "pic", "target", "respons", "jangan"):
        assert expected in tokens
    for stopword in ("berapa", "dan", "ke"):
        assert stopword not in tokens


def test_sparse_query_vector_is_deterministic():
    assert query_vector("tiket P1 P1") == query_vector("tiket P1")


def test_ids_are_deterministic():
    assert point_id("sha", "section", 4, None) == point_id("sha", "section", 4, None)
    assert point_id("sha", "section", 4, None) != point_id("sha2", "section", 4, None)
    assert doc_label("KB_01_Penanganan_Tiket_Layanan") == "KB_01"


def test_usage_reads_real_token_counts():
    message = SimpleNamespace(usage_metadata={"input_tokens": 120, "output_tokens": 30,
                                              "output_token_details": {"reasoning": 5}})
    usage = usage_from_message(message, node="answer", model="gemini-3.5-flash-lite", latency_ms=12.3)
    assert (usage.input_tokens, usage.output_tokens, usage.reasoning_tokens) == (120, 30, 5)
    summary = summarize([usage])
    assert summary["cost_usd"] > 0 and summary["unpriced_calls"] == 0


def test_valid_citation_passes_with_case_and_dash_differences():
    drafts = [{"evidence_id": "KB_01 §4", "quote": "p1: 15 MENIT;  P2: 1 jam"}]
    valid, invalid = check_citations(drafts, EVIDENCE)
    assert len(valid) == 1 and not invalid
    assert valid[0]["file_name"] == "KB_01_x.pdf" and valid[0]["pages"] == [1]


def test_fabricated_quote_is_rejected():
    valid, invalid = check_citations([{"evidence_id": "KB_01 §4", "quote": "P1: 1 jam"}], EVIDENCE)
    assert not valid and "not found verbatim" in invalid[0]["reason"]


def test_citation_to_unretrieved_evidence_is_rejected():
    valid, invalid = check_citations([{"evidence_id": "KB_04 §3", "quote": "P1: 15 menit"}], EVIDENCE)
    assert not valid and "not retrieved" in invalid[0]["reason"]


def test_unknown_inline_markers_are_removed():
    answer = "Target P1 adalah 15 menit [KB_01 §4]. SEV1 setiap 20 menit [KB_04 §5]."
    assert strip_unknown_markers(answer, {"KB_01 §4"}) == "Target P1 adalah 15 menit [KB_01 §4]. SEV1 setiap 20 menit."
