"""CLI: ask the SOP assistant a question.

    python -m app.ask "Berapa target respons awal untuk tiket P1?"
    python -m app.ask "..." --json        # full response incl. retrieval ranks, usage, timings
"""

import argparse
import asyncio
import json
import logging
import sys

from app.chat import ask
from app.config import get_settings
from app.graph.build import attach_graph
from app.services import build_services


def format_response(result: dict) -> str:
    lines = [f"[{result['status']}] {result['answer']}"]
    if result.get("missing"):
        lines.append(f"  Not specified in the SOPs: {result['missing']}")
    for citation in result["citations"]:
        pages = ",".join(str(p) for p in citation["pages"])
        section = f"§{citation['section_no']} {citation['section_title']}" if citation["section_no"] else "document overview"
        lines.append(f"  - {citation['file_name']}, page {pages}, {section}: \"{citation['quote']}\"")
    usage = result["usage"]
    lines.append(
        f"  ({result['timings_ms']['total'] / 1000:.1f}s · {usage['llm_calls']} LLM calls · "
        f"{usage['input_tokens']}+{usage['output_tokens']} tokens · judge: {result['judge']})"
    )
    return "\n".join(lines)


async def _main(question: str, top_k: int | None, as_json: bool) -> None:
    services = attach_graph(build_services(get_settings()))
    try:
        result = await ask(services, question, top_k=top_k)
    finally:
        await services.close()
    print(json.dumps(result, ensure_ascii=False, indent=2) if as_json else format_response(result))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    asyncio.run(_main(args.question, args.top_k, args.json))


if __name__ == "__main__":
    main()
