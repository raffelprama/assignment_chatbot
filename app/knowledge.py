"""In-memory view of the indexed documents, built from the artefacts.

Used for the normalize step's scope card, for catalogue questions ("which SOPs exist?"), and for
the whole-knowledge-base-in-the-prompt baseline in the evaluation.
"""

import json
from pathlib import Path

from app.ids import doc_label
from app.retrieval.hybrid import Evidence, evidence_id


class KnowledgeCatalog:
    def __init__(self, extracted_dir: Path):
        self._dir = extracted_dir
        self._artifacts: list[dict] = []
        self.refresh()

    def refresh(self) -> None:
        paths = sorted(self._dir.glob("*.json")) if self._dir.exists() else []
        self._artifacts = [json.loads(p.read_text(encoding="utf-8")) for p in paths]

    def remove(self, doc_id: str) -> None:
        self._artifacts = [a for a in self._artifacts if a["doc_id"] != doc_id]

    @property
    def titles(self) -> list[str]:
        return [a["title"] for a in self._artifacts]

    def scope_card(self) -> str:
        if not self._artifacts:
            return "(no documents indexed)"
        lines = []
        for artifact in self._artifacts:
            sections = "; ".join(s["title"] for s in artifact["sections"])
            lines.append(f"- {artifact['title']}: {sections}")
        return "\n".join(lines)

    def doc_maps(self) -> list[Evidence]:
        return [self._evidence(a, None) for a in self._artifacts]

    def all_sections(self) -> list[Evidence]:
        return [self._evidence(a, s) for a in self._artifacts for s in a["sections"]]

    @staticmethod
    def _evidence(artifact: dict, section: dict | None) -> Evidence:
        label = artifact.get("label") or doc_label(artifact["doc_id"])
        base = dict(doc_id=artifact["doc_id"], label=label, doc_title=artifact["title"],
                    file_name=artifact["file_name"], score=0.0)
        if section is None:
            pages = sorted({p for s in artifact["sections"] for p in s["pages"]})
            return Evidence(evidence_id=evidence_id(label, None, "docmap"), kind="docmap", pages=pages,
                            section_no=None, section_title=None, text=artifact["doc_map"], **base)
        return Evidence(evidence_id=evidence_id(label, section["section_no"], "section"), kind="section",
                        pages=section["pages"], section_no=section["section_no"],
                        section_title=section["title"], text=section["text"], **base)
