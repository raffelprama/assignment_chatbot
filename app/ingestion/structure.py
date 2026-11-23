"""Page text -> document title + sections, and a validator that fails loudly.

Numbered headings ("3. Tingkat Prioritas") become sections. A heading is accepted only if its
number is the next expected one, so "09.00-17.00" or a wrapped number never opens a section.
Documents without numbered headings fall back to paragraph windows.
"""

import re
from dataclasses import asdict, dataclass, field

from app.ingestion.extract import PageText

_HEADING = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
# A heading-like token for another section inside a body hints at column splicing.
_EMBEDDED_HEADING = re.compile(r"(?:^|\s)(\d{1,2})\.\s+[A-Z][a-z]{2,}")
_FALLBACK_WINDOW_CHARS = 900


@dataclass
class Section:
    section_no: int | None
    title: str
    text: str
    pages: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ParsedDocument:
    title: str
    structure: str  # "numbered" | "paragraphs"
    sections: list[Section]


def _looks_like_heading(rest: str) -> bool:
    return len(rest) <= 80 and rest[0].isupper() and not rest.rstrip().endswith((".", ",", ";"))


def _join(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _page_lines(pages: list[PageText]) -> list[tuple[int, str]]:
    lines = []
    for page in pages:
        for raw in page.text.splitlines():
            line = raw.strip()
            if line and not re.fullmatch(r"\d{1,3}", line):  # stray page numbers
                lines.append((page.page_no, line))
    return lines


def parse_document(pages: list[PageText], fallback_title: str) -> ParsedDocument:
    lines = _page_lines(pages)
    preamble: list[str] = []
    sections: list[Section] = []
    bodies: list[list[str]] = []
    expected = 1
    for page_no, line in lines:
        match = _HEADING.match(line)
        if match and int(match.group(1)) == expected and _looks_like_heading(match.group(2)):
            sections.append(Section(expected, match.group(2).strip(), "", [page_no]))
            bodies.append([])
            expected += 1
        elif sections:
            bodies[-1].append(line)
            if page_no not in sections[-1].pages:
                sections[-1].pages.append(page_no)
        else:
            preamble.append(line)
    title = preamble[0] if preamble else fallback_title
    if sections:
        for section, body in zip(sections, bodies):
            section.text = _join(body)
        return ParsedDocument(title, "numbered", sections)
    return ParsedDocument(title, "paragraphs", _paragraph_windows(lines[1:] if preamble else lines))


def _paragraph_windows(lines: list[tuple[int, str]]) -> list[Section]:
    sections: list[Section] = []
    buffer: list[str] = []
    pages: list[int] = []
    for page_no, line in lines:
        buffer.append(line)
        if page_no not in pages:
            pages.append(page_no)
        if sum(len(item) for item in buffer) >= _FALLBACK_WINDOW_CHARS:
            sections.append(Section(None, f"Bagian {len(sections) + 1}", _join(buffer), pages))
            buffer, pages = [], []
    if buffer:
        sections.append(Section(None, f"Bagian {len(sections) + 1}", _join(buffer), pages))
    return sections


def validate(doc: ParsedDocument) -> list[str]:
    """Return problems; an empty list means the structure is trustworthy enough to index."""
    problems = []
    if not doc.sections:
        problems.append("no sections extracted")
    for section in doc.sections:
        label = f"section {section.section_no or section.title}"
        if not section.text:
            problems.append(f"{label} has an empty body")
        for match in _EMBEDDED_HEADING.finditer(section.text):
            number = int(match.group(1))
            if section.section_no is not None and number != section.section_no:
                problems.append(f"{label} contains heading-like text '{match.group(0).strip()}' (column splice?)")
    return problems
