"""The whole chat graph against the real artefacts, an in-memory Qdrant and a scripted LLM.

This checks routing and the safety rules, not model quality (that is what eval/ measures).
"""

import json

import pytest

from app.chat import ask
from app.graph.build import attach_graph
from app.ingestion.indexer import index_artifact
from tests.conftest import EXTRACTED_DIR, UNAVAILABLE

DOC = "KB_01_Penanganan_Tiket_Layanan"
NORMALIZED = {"intent": "in_scope", "search_query": "target respons awal tiket P1",
              "answer_language": "id", "reason": "test"}
GOOD_ANSWER = {"status": "answered", "answer": "Target respons awal P1 adalah 15 menit [KB_01 §4].",
               "citations": [{"evidence_id": "KB_01 §4", "quote": "P1: 15 menit"}], "missing": ""}
PASS = {"verdict": "pass", "reason": "supported"}


async def _services(make_services, script):
    services = attach_graph(make_services(script))
    artifact = json.loads((EXTRACTED_DIR / f"{DOC}.json").read_text(encoding="utf-8"))
    await index_artifact(artifact, services.store, services.embedder)
    return services


@pytest.mark.asyncio
async def test_happy_path_returns_checked_citation(make_services):
    services = await _services(make_services, {"normalize": NORMALIZED, "answer": GOOD_ANSWER, "judge": PASS})
    result = await ask(services, "Berapa target respons awal untuk tiket P1?")
    assert result["status"] == "answered"
    assert result["citations"][0]["evidence_id"] == "KB_01 §4"
    assert result["citations"][0]["file_name"].startswith("KB_01") and result["citations"][0]["pages"] == [1]
    assert result["route"] == ["normalize", "retrieve", "answer", "check_citations", "judge", "respond"]
    assert result["usage"]["input_tokens"] > 0


@pytest.mark.asyncio
async def test_answer_with_fabricated_quote_is_never_shown(make_services):
    fabricated = {**GOOD_ANSWER, "citations": [{"evidence_id": "KB_01 §4", "quote": "P1: 1 hari"}]}
    services = await _services(make_services, {"normalize": NORMALIZED, "answer": fabricated, "judge": PASS})
    result = await ask(services, "Berapa target respons awal untuk tiket P1?")
    assert result["status"] == "no_answer" and not result["citations"]
    assert "tidak ditemukan" in result["answer"]
    assert "judge" not in result["route"]  # nothing to judge


@pytest.mark.asyncio
async def test_off_domain_question_is_declined_without_retrieval(make_services):
    off = {**NORMALIZED, "intent": "off_domain"}
    services = await _services(make_services, {"normalize": off})
    result = await ask(services, "Apa ibu kota Prancis?")
    assert result["status"] == "out_of_scope"
    assert result["route"] == ["normalize", "respond"]


@pytest.mark.asyncio
async def test_normalize_outage_continues_instead_of_refusing(make_services):
    services = await _services(make_services, {"normalize": UNAVAILABLE, "answer": GOOD_ANSWER, "judge": PASS})
    result = await ask(services, "Berapa target respons awal untuk tiket P1?")
    assert result["status"] == "answered"


@pytest.mark.asyncio
async def test_judge_outage_keeps_a_citation_checked_answer(make_services):
    services = await _services(make_services, {"normalize": NORMALIZED, "answer": GOOD_ANSWER, "judge": UNAVAILABLE})
    result = await ask(services, "Berapa target respons awal untuk tiket P1?")
    assert result["status"] == "answered" and result["judge"] == "unavailable"


@pytest.mark.asyncio
async def test_incomplete_verdict_widens_retrieval_once_then_flags_partial(make_services):
    incomplete = {"verdict": "incomplete", "missing_aspects": ["P2 target"], "reason": "x"}
    services = await _services(make_services, {"normalize": NORMALIZED, "answer": GOOD_ANSWER, "judge": incomplete})
    result = await ask(services, "Target P1 dan P2?")
    assert result["route"].count("retrieve") == 2 and result["route"].count("judge") == 2
    assert result["status"] == "partial" and "P2 target" in result["missing"]


@pytest.mark.asyncio
async def test_unsupported_verdict_regenerates_once_then_refuses(make_services):
    unsupported = {"verdict": "unsupported", "unsupported_claims": ["P1 = SEV1"], "reason": "x"}
    services = await _services(make_services, {"normalize": NORMALIZED, "answer": GOOD_ANSWER, "judge": unsupported})
    result = await ask(services, "Apakah P1 sama dengan SEV1?")
    assert result["route"].count("answer") == 2 and result["route"].count("retrieve") == 1
    assert result["status"] == "no_answer" and not result["citations"]


@pytest.mark.asyncio
async def test_catalog_intent_returns_every_document_map(make_services):
    catalog = {**NORMALIZED, "intent": "catalog"}

    def answer(messages):
        assert messages[1].content.count("peta-dokumen") == 4  # all four document maps were given
        return {"status": "answered", "answer": "Ada empat SOP [KB_01 peta-dokumen].",
                "citations": [{"evidence_id": "KB_01 peta-dokumen", "quote": "Penanganan Tiket Layanan"}]}

    services = await _services(make_services, {"normalize": catalog, "answer": answer, "judge": PASS})
    result = await ask(services, "Dokumen SOP apa saja yang tersedia?")
    assert result["status"] == "answered" and result["citations"][0]["section_no"] is None
