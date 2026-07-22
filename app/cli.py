"""Command-line interface.

    unified-api collect [--connector NAME ...]   # fetch + store
    unified-api list [--source S] [--type T]     # show stored records
    unified-api connectors                        # list available connectors
    unified-api serve [--host H] [--port P]      # run the HTTP API
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.orchestrator import CollectionSelection
from app.platform import Platform


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="unified-api", description=__doc__)
    parser.add_argument("--config", default=None, help="path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="fetch from connectors and store results")
    collect.add_argument(
        "--connector",
        action="append",
        dest="connectors",
        help="connector name (repeatable); defaults to all enabled",
    )

    listing = sub.add_parser("list", help="list stored records")
    listing.add_argument("--source")
    listing.add_argument("--type", dest="record_type")
    listing.add_argument("--limit", type=int, default=20)

    sub.add_parser("connectors", help="list available connectors")

    serve = sub.add_parser("serve", help="run the FastAPI server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    return parser


async def _run_collect(platform: Platform, connectors: list[str] | None) -> int:
    selections = (
        [CollectionSelection(connector=name) for name in connectors]
        if connectors
        else None
    )
    async with platform:
        summary = await platform.orchestrator.collect(selections)
    print(json.dumps(summary.model_dump(), indent=2, ensure_ascii=False))
    return 0 if all(r.status == "ok" for r in summary.results) else 1


async def _run_list(
    platform: Platform, source: str | None, record_type: str | None, limit: int
) -> int:
    async with platform:
        rows = await platform.repository.list_records(
            source=source, record_type=record_type, limit=limit
        )
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


async def _run_connectors(platform: Platform) -> int:
    async with platform:
        print(json.dumps(platform.orchestrator.available(), indent=2))
    return 0


def _force_utf8_stdout() -> None:
    """Ensure JSON (which may contain emoji) prints on any console, incl. Windows cp1252."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    args = _build_parser().parse_args(argv)

    if args.command == "serve":
        import uvicorn

        uvicorn.run("app.api.app:app", host=args.host, port=args.port, reload=False)
        return 0

    platform = Platform.from_config_file(args.config)

    if args.command == "collect":
        return asyncio.run(_run_collect(platform, args.connectors))
    if args.command == "list":
        return asyncio.run(_run_list(platform, args.source, args.record_type, args.limit))
    if args.command == "connectors":
        return asyncio.run(_run_connectors(platform))

    return 2  # unreachable: argparse enforces a valid command


if __name__ == "__main__":
    sys.exit(main())
