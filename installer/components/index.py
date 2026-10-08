import os
import platform as system_platform
from pathlib import Path

from installer import api, fsutil, shell
from installer.components import model, ollama, vault
from installer.model import Context, Platform, Result, Support
from vault_search.config import DEFAULT_INDEX_DIRNAME, EMBED_DIMENSIONS

KEY = "index"
TITLE = "Suchindex erstellen"
DESCRIPTION = "Markdown-Dateien lokal einlesen und als Vektoren speichern."
DEFAULT = True


def supported(platform: Platform) -> Support:
    machine = system_platform.machine().lower()
    if (platform == "macos" and machine in {"x86_64", "amd64"}) or (
        platform == "windows" and machine in {"arm64", "aarch64"}
    ):
        return Support(
            "nein", f"LanceDB bietet für diese Plattform keine Wheels: {platform} {machine}."
        )
    return Support("ja")


def index_directory(ctx: Context) -> Path:
    root = vault.validate(ctx.values.get("vault", ""))
    return Path(os.environ.get("VAULT_INDEX_DIR", root / DEFAULT_INDEX_DIRNAME)).expanduser()


def settings(ctx: Context) -> dict[str, str]:
    return {
        "vault": str(vault.validate(ctx.values.get("vault", ""))),
        "model": model.model_name(ctx),
        "url": api.base_url(),
        "dimensions": os.environ.get("VAULT_EMBED_DIM", str(EMBED_DIMENSIONS)),
        "ignore": os.environ.get("VAULT_IGNORE_DIRS", ""),
    }


def is_done(ctx: Context) -> bool:
    marker = index_directory(ctx) / "installer.json"
    return fsutil.read_json(marker, {}) == settings(ctx)


def plan(ctx: Context) -> list[str]:
    return [
        f"Vollindex für {ctx.values.get('vault', 'den gewählten Vault')} "
        f"mit {model.model_name(ctx)} erstellen."
    ]


def apply(ctx: Context) -> Result:
    root = vault.validate(ctx.values.get("vault", ""))
    if not ollama.is_done(ctx):
        return Result(KEY, "handarbeit", ollama.MANUAL_START)
    if not model.is_done(ctx):
        return Result(
            KEY,
            "handarbeit",
            "Embedding-Modell fehlt. Installer mit --only modell erneut ausführen.",
        )
    uv = shell.which("uv")
    if not uv:
        return Result(
            KEY,
            "handarbeit",
            "uv installieren: https://docs.astral.sh/uv/getting-started/installation/",
        )
    environment = dict(os.environ, VAULT_ROOT=str(root), VAULT_EMBED_MODEL=model.model_name(ctx))
    shell.run(
        [uv, "--directory", ctx.values["repo"], "run", "--no-dev", "vault-reindex", "--full"],
        ctx,
        env=environment,
    )
    marker = index_directory(ctx) / "installer.json"
    fsutil.write_json(marker, settings(ctx))
    return Result(
        KEY, "erledigt", "Vollindex erstellt. Für spätere Änderungen vault-reindex ausführen."
    )
