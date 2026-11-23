"""Column order, routing quality checks and section parsing, on the real KB files (no LLM)."""

import pytest
from pypdf import PdfReader

from app.ingestion.extract import (PageText, collect_runs, naive_position_order, order_text,
                                   text_quality)
from app.ingestion.structure import parse_document, validate
from tests.conftest import KB_DIR

KB_03 = KB_DIR / "KB_03_Panduan_Operasional_Layanan.pdf"


def _page(path):
    page = PdfReader(path).pages[0]
    return page, float(page.mediabox.width), float(page.mediabox.height)


def test_two_column_page_is_read_column_by_column():
    page, width, height = _page(KB_03)
    text, layout = order_text(collect_runs(page), width, height)
    doc = parse_document([PageText(1, "text_layer", layout, text, "")], "KB_03")
    assert layout == "two_column"
    assert [s.section_no for s in doc.sections] == list(range(1, 9))
    assert doc.sections[0].text.startswith("Layanan reguler beroperasi")
    assert validate(doc) == []


def test_naive_position_order_splices_columns_and_validator_catches_it():
    page, _, _ = _page(KB_03)
    naive = PageText(1, "text_layer", "unknown", naive_position_order(collect_runs(page)), "")
    doc = parse_document([naive], "KB_03")
    assert [s.section_no for s in doc.sections] == list(range(1, 7))  # §7, §8 swallowed
    assert any("column splice" in problem for problem in validate(doc))


def test_page_number_is_not_part_of_the_text():
    page, width, height = _page(KB_DIR / "KB_02_Pengelolaan_Keluhan_Pelanggan.pdf")
    text, layout = order_text(collect_runs(page), width, height)
    assert layout == "single_column"
    assert "\n1\n" not in f"\n{text}\n"


def test_scanned_page_has_no_usable_text_layer():
    page, width, height = _page(KB_DIR / "KB_01_Penanganan_Tiket_Layanan.pdf")
    runs = collect_runs(page)
    text = order_text(runs, width, height)[0] if runs else ""
    usable, _ = text_quality(text, min_chars=40)
    assert not usable


@pytest.mark.parametrize("text, reason", [
    ("(cid:12)(cid:4)(cid:9)(cid:1)(cid:7)(cid:22)(cid:3) " * 10, "glyph-id"),
    ("12 34 56 78 90 11 22 33 44 55 66 77 88 99 00 12 34 56 78", "letter ratio"),
    ("abc", "too little"),
])
def test_text_quality_rejects_unreadable_layers(text, reason):
    usable, why = text_quality(text, min_chars=20)
    assert not usable and reason in why


def test_heading_needs_the_next_number_in_sequence():
    text = ("Judul\n1. Jam Layanan\nLayanan pukul\n09.00-17.00 WIB.\n3. Bukan Heading\n"
            "2. Serah Terima\nIsi kedua.")
    doc = parse_document([PageText(1, "text_layer", "single_column", text, "")], "x")
    assert [(s.section_no, s.title) for s in doc.sections] == [(1, "Jam Layanan"), (2, "Serah Terima")]
    assert "09.00-17.00" in doc.sections[0].text


def test_unnumbered_document_falls_back_to_paragraph_windows():
    lines = "\n".join(f"Kalimat panjang nomor {i} tentang prosedur layanan pelanggan." for i in range(60))
    doc = parse_document([PageText(1, "text_layer", "single_column", f"Judul Dokumen\n{lines}", "")], "x")
    assert doc.structure == "paragraphs"
    assert len(doc.sections) >= 2 and all(s.section_no is None for s in doc.sections)
