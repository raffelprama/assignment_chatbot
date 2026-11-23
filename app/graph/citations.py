"""Deterministic citation check: the safety layer that cannot fail open.

A citation is valid only if its evidence was actually retrieved for this question AND its quote
appears verbatim (up to case, whitespace and dash/quote style) in that evidence's text. Inline
markers pointing at anything else are removed. An answer left with no valid citation is never
shown as an answer.
"""

import re
import unicodedata

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_QUOTES = dict.fromkeys(map(ord, "‘’“”«»"), '"')
_MARKER = re.compile(r"\s?\[([^\[\]]{2,80})\]")


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_QUOTES).casefold()
    return re.sub(r"\s+", " ", text).strip().strip('"').strip()


def check_citations(drafts: list[dict], evidence: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split draft citations into (valid, invalid); valid ones are enriched with source metadata."""
    by_id = {item["evidence_id"]: item for item in evidence}
    valid, invalid, seen = [], [], set()
    for draft in drafts:
        source = by_id.get(draft["evidence_id"].strip())
        quote = draft["quote"].strip()
        quote_norm = normalize_for_match(quote).rstrip(".")
        if source is None:
            invalid.append({**draft, "reason": "evidence was not retrieved for this question"})
            continue
        if not quote_norm or quote_norm not in normalize_for_match(source["text"]):
            invalid.append({**draft, "reason": "quote not found verbatim in the evidence"})
            continue
        key = (source["evidence_id"], quote_norm)
        if key in seen:
            continue
        seen.add(key)
        valid.append({
            "evidence_id": source["evidence_id"],
            "doc_id": source["doc_id"],
            "doc_title": source["doc_title"],
            "file_name": source["file_name"],
            "pages": source["pages"],
            "section_no": source["section_no"],
            "section_title": source["section_title"],
            "quote": quote,
        })
    return valid, invalid


def strip_unknown_markers(answer: str, allowed_ids: set[str]) -> str:
    """Remove inline [..] markers whose ids are not among the validated citations."""
    def keep(match: re.Match) -> str:
        ids = [part.strip() for part in re.split(r"[;,]", match.group(1))]
        kept = [i for i in ids if i in allowed_ids]
        return f" [{'; '.join(kept)}]" if kept else ""

    return _MARKER.sub(keep, answer).strip()
