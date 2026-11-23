"""Local BM25 sparse vectors for Qdrant (IDF is applied server-side via `Modifier.IDF`).

The tokenizer deliberately keeps short tokens such as `p1`, `p2`, `sev1`, `otp`, `pin`, `pic`:
in SOP text they are the most discriminative words there are, and many default tokenizers drop
anything shorter than three characters.
"""

import re
import unicodedata
import zlib

_TOKEN = re.compile(r"[0-9a-z]+")

STOPWORDS = frozenset(
    # Indonesian function words and question words
    "yang dan di ke dari untuk dengan atau pada dalam adalah ini itu apa apakah bagaimana berapa "
    "kapan siapa mana dimana mengapa kenapa saja akan sudah telah oleh bila jika apabila agar "
    "sebagai serta juga dapat bisa ada para kami saya kamu anda kita tersebut setiap secara "
    "nya lah kah pun gimana gmn kalo kalau aja dong sih ya "
    # English function words and question words
    "the a an of to in on at is are was were be been what how when who whom which why where "
    "for and or with by from as it its this that these those do does did can could should "
    "would will shall may might must i you we they he she there".split()
)

_K1 = 1.2
_B = 0.75


def tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return [tok for tok in _TOKEN.findall(normalized) if tok not in STOPWORDS]


def token_id(token: str) -> int:
    return zlib.crc32(token.encode("utf-8"))


def document_vector(text: str, avg_doc_len: float) -> tuple[list[int], list[float]]:
    """BM25 term-frequency component; Qdrant multiplies by IDF at query time."""
    tokens = tokenize(text)
    counts: dict[str, int] = {}
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1
    length_norm = 1 - _B + _B * (len(tokens) / max(avg_doc_len, 1.0))
    weights = {
        token_id(tok): tf * (_K1 + 1) / (tf + _K1 * length_norm) for tok, tf in counts.items()
    }
    return list(weights), list(weights.values())


def query_vector(text: str) -> tuple[list[int], list[float]]:
    ids = sorted({token_id(tok) for tok in tokenize(text)})
    return ids, [1.0] * len(ids)
