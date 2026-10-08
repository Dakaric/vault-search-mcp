from installer import api, shell, ui
from installer.model import Context, Platform, Result, Support
from installer.platform import cache_dir

KEY = "ollama"
TITLE = "Ollama bereitstellen"
DESCRIPTION = "Lokalen Dienst für Embeddings prüfen und bei Bedarf installieren."
DEFAULT = True
MANUAL_START = "Ollama starten und Installer erneut ausführen."
DOWNLOAD = "Ollama von https://ollama.com/download installieren. " + MANUAL_START


def supported(platform: Platform) -> Support:
    return Support("ja")


def is_done(ctx: Context) -> bool:
    try:
        api.request("/api/version")
        return True
    except api.ApiError:
        return False


def plan(ctx: Context) -> list[str]:
    return [f"Ollama unter {api.base_url()} prüfen; bei Bedarf Installation anbieten."]


def _install_linux(ctx: Context) -> bool:
    curl, interpreter = shell.which("curl"), shell.which("sh")
    if not curl or not interpreter:
        return False
    if not ui.ask_yes_no(
        "Offizielles Ollama-Skript herunterladen und ausführen (kann sudo benötigen)?", False, ctx
    ):
        return False
    folder = cache_dir("vault-search-mcp", ctx)
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / "ollama-install.sh"
    shell.run([curl, "-fsSL", "https://ollama.com/install.sh", "-o", str(script)], ctx)
    shell.run([interpreter, str(script)], ctx)
    return True


def apply(ctx: Context) -> Result:
    if is_done(ctx):
        return Result(KEY, "erledigt", "Ollama ist erreichbar.")
    if shell.which("ollama"):
        return Result(KEY, "handarbeit", MANUAL_START)
    if ctx.platform == "macos" and (brew := shell.which("brew")):
        shell.run([brew, "install", "ollama"], ctx)
        shell.run([brew, "services", "start", "ollama"], ctx)
    elif ctx.platform == "windows" and (winget := shell.which("winget")):
        shell.run(
            [
                winget,
                "install",
                "--id",
                "Ollama.Ollama",
                "-e",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            ctx,
        )
        return Result(KEY, "handarbeit", "Neues Terminal öffnen und Installer erneut starten.")
    elif ctx.platform != "linux" or not _install_linux(ctx):
        return Result(KEY, "handarbeit", DOWNLOAD)
    if is_done(ctx):
        return Result(KEY, "erledigt", "Ollama ist erreichbar.")
    return Result(KEY, "handarbeit", MANUAL_START)
