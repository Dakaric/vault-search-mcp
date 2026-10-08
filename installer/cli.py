import argparse
import os
import sys
from pathlib import Path

from installer import platform, ui
from installer.components import COMPONENTS, vault
from installer.model import Context
from installer.run import run_components
from vault_search.config import DEFAULT_EMBED_MODEL


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lokale Vault-Suche einrichten.")
    parser.add_argument("--yes", action="store_true", help="Standardantworten verwenden.")
    parser.add_argument(
        "--only", help="Bausteine, durch Kommas getrennt: ollama,modell,vault,index,registrieren."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur den Plan anzeigen, ohne Dienstabfragen oder Änderungen.",
    )
    parser.add_argument(
        "--vault",
        default=os.environ.get("VAULT_ROOT", ""),
        help="Absoluter Pfad zu einem vorhandenen Vault.",
    )
    parser.add_argument("--model", default=DEFAULT_EMBED_MODEL, help="Embedding-Modell in Ollama.")
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = _parser().parse_args(argv)
    if not args.yes and not sys.stdin.isatty():
        print("Kein interaktives Terminal. Bitte --yes und die benötigten Werte angeben.")
        return 2
    only = (
        {key.strip() for key in args.only.split(",") if key.strip()}
        if args.only is not None
        else None
    )
    if only is not None and (not only or only - {c.KEY for c in COMPONENTS}):
        print("Unbekannte oder leere Bausteinauswahl. Siehe --help.")
        return 2
    try:
        ctx = Context(
            platform.detect(),
            Path.home(),
            args.dry_run,
            args.yes,
            {
                "vault": args.vault,
                "model": args.model,
                "repo": str(Path(__file__).resolve().parents[1]),
            },
        )
        if only is None or only & {"vault", "index", "registrieren"}:
            value = args.vault or ui.ask_text("Absoluter Vault-Pfad?", "", ctx)
            ctx.values["vault"] = str(vault.validate(value))
        results = run_components(COMPONENTS, ctx, only)
    except (ValueError, EOFError) as error:
        print(error)
        return 2
    ui.print_summary(results)
    return 1 if any(result.status == "fehler" for result in results) else 0
