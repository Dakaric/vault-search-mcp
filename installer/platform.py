import os
import sys
from pathlib import Path

from installer.model import Context, Platform


def detect() -> Platform:
    names: dict[str, Platform] = {"darwin": "macos", "linux": "linux", "win32": "windows"}
    try:
        return names[sys.platform]
    except KeyError:
        raise ValueError(f"Betriebssystem nicht unterstützt: {sys.platform}") from None


def cache_dir(app: str, ctx: Context) -> Path:
    if ctx.platform == "windows":
        return Path(os.environ.get("LOCALAPPDATA", ctx.home / "AppData" / "Local")) / app / "cache"
    return ctx.home / ".cache" / app
