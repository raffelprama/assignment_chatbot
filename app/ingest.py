"""CLI: ingest PDFs into the index.

    python -m app.ingest                      # all PDFs in data/kb/
    python -m app.ingest path/a.pdf --rebuild # re-extract even if an artefact exists
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from app.config import get_settings
from app.ingestion.service import ingest_pdf
from app.services import build_services


async def _main(paths: list[Path], rebuild: bool) -> None:
    services = build_services(get_settings())
    try:
        for path in paths:
            report = await ingest_pdf(services, path.read_bytes(), path.name, rebuild=rebuild)
            extraction = report["extraction"]
            print(json.dumps({
                "doc_id": report["doc_id"],
                "title": report["title"],
                "reused_artifact": report["reused_artifact"],
                "pages_by_method": extraction["pages_by_method"],
                "layouts": extraction["layouts"],
                "sections": extraction["sections"],
                "keys": extraction["keys"],
                "points": report["index"]["by_kind"],
                "smoke_test_failed": report["index"]["smoke_test"]["failed"],
            }, ensure_ascii=False))
    finally:
        await services.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--rebuild", action="store_true", help="re-extract even if an artefact exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    paths = args.paths or sorted((get_settings().data_dir / "kb").glob("*.pdf"))
    asyncio.run(_main(paths, args.rebuild))


if __name__ == "__main__":
    main()
