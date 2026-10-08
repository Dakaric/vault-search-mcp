from installer import api
from installer.components import ollama
from installer.model import Context, Platform, Result, Support
from vault_search.config import DEFAULT_EMBED_MODEL

KEY = "modell"
TITLE = "Embedding-Modell laden"
DESCRIPTION = "Modell über die Ollama-API herunterladen."
DEFAULT = True


def supported(platform: Platform) -> Support:
    return Support("ja")


def model_name(ctx: Context) -> str:
    return ctx.values.get("model", DEFAULT_EMBED_MODEL)


def is_done(ctx: Context) -> bool:
    try:
        models = api.request("/api/tags").get("models", [])
    except api.ApiError:
        return False
    selected = model_name(ctx)
    normalized = selected if ":" in selected else selected + ":latest"
    return any(
        (name if ":" in name else name + ":latest") == normalized
        for item in models
        if isinstance(item, dict)
        for name in [item.get("name", "")]
        if name
    )


def plan(ctx: Context) -> list[str]:
    return [f"Modell {model_name(ctx)} prüfen und bei Bedarf laden."]


def apply(ctx: Context) -> Result:
    if not ollama.is_done(ctx):
        return Result(KEY, "handarbeit", ollama.MANUAL_START)
    api.request("/api/pull", data={"model": model_name(ctx), "stream": False}, timeout=1800)
    return Result(KEY, "erledigt", f"Modell {model_name(ctx)} ist geladen.")
