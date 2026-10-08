from __future__ import annotations

import argparse
import sys
import time

from vault_graph import queries
from vault_graph.render import render
from vault_graph.store import GraphStore
from vault_search.config import Config, ConfigError


def _global_options() -> argparse.ArgumentParser:
    g = argparse.ArgumentParser(add_help=False)
    g.add_argument("--agent", action="store_true", help="JSON-Envelope statt Tabelle.")
    g.add_argument("--limit", type=int, default=None, help="Ergebnis begrenzen.")
    g.add_argument("--no-refresh", action="store_true", help="Fresh-on-read überspringen.")
    return g


def _build_parser() -> argparse.ArgumentParser:
    glob = _global_options()
    p = argparse.ArgumentParser(
        prog="vault-graph",
        description="Struktur-Queries über den Vault.",
        parents=[glob],
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[glob])

    add("orphans")
    add("broken")
    add("stats")
    add("doctor")

    bl = add("backlinks")
    bl.add_argument("title")
    lk = add("links")
    lk.add_argument("title")

    td = add("todos")
    td.add_argument("--folder", default=None)
    td.add_argument("--note", default=None)

    st = add("stale")
    st.add_argument("--days", type=int, default=30)
    st.add_argument(
        "--folder",
        default="",
        help="Ordner-Filter; leer = alle.",
    )

    qy = add("query")
    qy.add_argument("--status", default=None)
    qy.add_argument("--folder", default=None)
    qy.add_argument("--quelle", default=None)

    tg = add("tags")
    tg.add_argument("--cooccur", action="store_true")

    dl = add("daily")
    dl.add_argument("--gaps", action="store_true")
    return p


def _dispatch(args, conn) -> list[dict] | dict:
    cmd = args.command
    if cmd == "backlinks":
        return queries.backlinks(conn, args.title)
    if cmd == "links":
        return queries.outgoing_links(conn, args.title)
    if cmd == "orphans":
        return queries.orphans(conn)
    if cmd == "broken":
        return queries.broken(conn)
    if cmd == "todos":
        return queries.todos(conn, folder=args.folder, note=args.note)
    if cmd == "stale":
        return queries.stale(conn, days=args.days, now=time.time(), folder=args.folder or None)
    if cmd == "query":
        filters = {
            k: v
            for k, v in (
                ("status", args.status),
                ("folder", args.folder),
                ("quelle", args.quelle),
            )
            if v is not None
        }
        return queries.query_frontmatter(conn, filters)
    if cmd == "tags":
        return queries.tags(conn, cooccur=args.cooccur)
    if cmd == "daily":
        return queries.daily(conn, gaps=args.gaps)
    if cmd == "stats":
        return queries.stats(conn)
    if cmd == "doctor":
        return queries.doctor(conn)
    raise ValueError(f"Unbekanntes Kommando: {cmd}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    try:
        config = Config.from_env()
    except ConfigError as error:
        print(error)
        return 2
    store = GraphStore(config.index_dir / "graph.db")
    refreshed = 0
    if not args.no_refresh:
        refreshed = store.refresh(config.vault_root, config.ignore_dirs, config.daily_dir)[
            "indexed"
        ]

    result = _dispatch(args, store.conn)

    if isinstance(result, dict):
        rows = [result]
    else:
        rows = result
        if args.limit is not None:
            rows = rows[: args.limit]

    print(render(args.command, rows, refreshed=refreshed, agent=args.agent))
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
