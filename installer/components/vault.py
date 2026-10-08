from pathlib import Path

from installer import ui
from installer.model import Context, Platform, Result, Support

KEY = "vault"
TITLE = "Vault auswählen"
DESCRIPTION = "Vorhandenen Markdown-Vault prüfen. Notizen bleiben unverändert."
DEFAULT = True


def supported(platform: Platform) -> Support:
    return Support("ja")


def is_done(ctx: Context) -> bool:
    return False


def plan(ctx: Context) -> list[str]:
    return ["Vorhandenen Vault prüfen: " + ctx.values.get("vault", "Pfad wird abgefragt")]


def validate(value: str) -> Path:
    path = Path(value).expanduser()
    if not value or not path.is_absolute() or not path.is_dir():
        raise ValueError("Der Vault muss ein vorhandener Ordner mit absolutem Pfad sein.")
    return path.resolve()


def apply(ctx: Context) -> Result:
    value = ctx.values.get("vault", "") or ui.ask_text("Absoluter Vault-Pfad?", "", ctx)
    try:
        path = validate(value)
    except ValueError as error:
        return Result(KEY, "fehler", str(error))
    ctx.values["vault"] = str(path)
    return Result(KEY, "erledigt", str(path))
