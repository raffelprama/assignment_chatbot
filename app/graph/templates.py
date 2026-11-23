"""Fixed replies for refusals. Templates, not generated text, so they cannot hallucinate."""

_TEMPLATES = {
    "no_answer": {
        "id": "Maaf, informasi tersebut tidak ditemukan dalam dokumen SOP yang tersedia. "
              "Silakan ajukan pertanyaan dengan kata lain, atau konfirmasi kepada pihak yang berwenang.",
        "en": "Sorry, I could not find this information in the available SOP documents. "
              "Try rephrasing the question, or confirm with the responsible team.",
    },
    "out_of_scope": {
        "id": "Pertanyaan ini berada di luar cakupan dokumen SOP yang tersedia ({titles}). "
              "Saya hanya dapat menjawab berdasarkan isi dokumen tersebut.",
        "en": "This question is outside the scope of the available SOP documents ({titles}). "
              "I can only answer from the content of those documents.",
    },
    "unsafe": {
        "id": "Saya tidak dapat memproses permintaan tersebut. Saya hanya menjawab pertanyaan tentang isi dokumen SOP.",
        "en": "I can't help with that request. I only answer questions about the content of the SOP documents.",
    },
    "unverified": {
        "id": "Maaf, saya tidak dapat menyusun jawaban yang seluruhnya didukung oleh dokumen SOP untuk pertanyaan ini. "
              "Silakan periksa langsung dokumen terkait atau ajukan pertanyaan yang lebih spesifik.",
        "en": "Sorry, I could not produce an answer fully supported by the SOP documents for this question. "
              "Please check the relevant document directly or ask a more specific question.",
    },
}


def render(kind: str, language: str, titles: list[str] | None = None) -> str:
    variants = _TEMPLATES[kind]
    text = variants.get(language) or variants["en"]
    return text.format(titles=", ".join(titles or []))
