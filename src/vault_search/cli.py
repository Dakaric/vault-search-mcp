from __future__ import annotations

import argparse
import sys
import time

from .config import Config, ConfigError
from .indexer import reindex as run_reindex


def reindex() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Voll- oder Inkrementell-Index des Vaults.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Voll-Reindex (ignoriert bestehende mtimes und indexiert alles neu).",
    )
    args = parser.parse_args()

    try:
        config = Config.from_env()
    except ConfigError as error:
        print(error)
        return 2
    print(f"Vault:   {config.vault_root}")
    print(f"Index:   {config.index_dir}")
    print(f"Modell:   {config.embed_model} ({config.embed_dim}d) @ {config.ollama_url}")
    print(f"Modus:   {'voll' if args.full else 'inkrementell'}")

    start = time.time()
    try:
        stats = run_reindex(config, incremental=not args.full)
    except ValueError as error:
        print(error)
        return 2
    elapsed = time.time() - start

    print(
        f"Fertig in {elapsed:.1f}s: {stats.scanned} geprüft, "
        f"{stats.indexed} indiziert, {stats.skipped} übersprungen, "
        f"{stats.deleted} entfernt, {stats.chunks} Textabschnitte geschrieben."
    )

    return 0


def selfcheck() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from .selfcheck import _FETCH, DEFAULT_THRESHOLD, run_selfcheck

    parser = argparse.ArgumentParser(
        description="Self-Retrieval-Check: welche Kernnotizen finden sich nicht selbst?"
    )
    parser.add_argument("--scope", default="", help="Kommagetrennte rel. Pfad-Präfixe.")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=f"Optional: Distanz-Cutoff (z.B. {DEFAULT_THRESHOLD}) simuliert "
        "das Live-Schwellen-Gate. Ohne = reiner Notiz-Rang (empfohlen, "
        "kurze Titel/alias-Queries ranken systematisch weiter als die "
        "kalibrierten Fragen).",
    )
    args = parser.parse_args()

    try:
        config = Config.from_env()
    except ConfigError as error:
        print(error)
        return 2
    scope = [s.strip() for s in args.scope.split(",") if s.strip()]
    weak = run_selfcheck(config, scope_prefixes=scope, top_k=args.top_k, threshold=args.threshold)

    if not weak:
        print(f"OK, alle Titel/aliases unter {scope} finden ihre Notiz in Top-{args.top_k}.")
        return 0
    fetched = max(args.top_k, _FETCH)
    gate = f", Schwelle {args.threshold}" if args.threshold is not None else ""
    print(
        f"{len(weak)} schwache (Notiz, Suchbegriff)-Paar(e), Query findet die Notiz "
        f"nicht in Top-{args.top_k}{gate}:\n"
    )
    for w in weak:
        if w.self_rank is not None and w.self_distance is not None:
            rank = f"Rang {w.self_rank} (d={w.self_distance:.3f})"
        else:
            rank = f"nicht in Top-{fetched}"
        print(
            f"  ✗ '{w.query}' → {w.path}\n"
            f"      Notiz selbst: {rank}\n"
            f"      oben stattdessen: {w.top_paths}"
        )
    # Ein eigener Exit-Code lässt Automatisierungen schwache Treffer erkennen.
    return 2


if __name__ == "__main__":
    sys.exit(reindex())
