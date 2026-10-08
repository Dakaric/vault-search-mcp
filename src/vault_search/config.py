from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INDEX_DIRNAME = ".vault-index"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_EMBED_MODEL = "mxbai-embed-large"
EMBED_DIMENSIONS = 1024
DEFAULT_DAILY_DIR = "05 Daily Notes"
DEFAULT_IGNORE_DIRS = (
    ".obsidian",
    ".trash",
    ".git",
    ".vault-index",
    ".vault-mcp-state",
    ".claude",
    "node_modules",
    ".venv",
)


class ConfigError(ValueError):
    """Ungültige oder fehlende Vault-Konfiguration."""


@dataclass(frozen=True)
class Config:
    vault_root: Path
    index_dir: Path
    ollama_url: str
    embed_model: str
    embed_dim: int
    ignore_dirs: tuple[str, ...] = DEFAULT_IGNORE_DIRS
    daily_dir: str = DEFAULT_DAILY_DIR

    @classmethod
    def from_env(cls) -> Config:
        root_value = os.environ.get("VAULT_ROOT", "").strip()
        if not root_value:
            raise ConfigError("VAULT_ROOT ist nicht gesetzt. Bitte den Vault-Pfad angeben.")
        vault_root = Path(root_value).expanduser().resolve()
        if not vault_root.is_dir():
            raise ConfigError("Vault ist kein erreichbarer Ordner: " + str(vault_root))
        try:
            dimensions = int(os.environ.get("VAULT_EMBED_DIM", EMBED_DIMENSIONS))
        except ValueError:
            raise ConfigError("VAULT_EMBED_DIM muss eine positive ganze Zahl sein.") from None
        if dimensions <= 0:
            raise ConfigError("VAULT_EMBED_DIM muss eine positive ganze Zahl sein.")
        extra_dirs = [
            item.strip()
            for item in os.environ.get("VAULT_IGNORE_DIRS", "").split(",")
            if item.strip()
        ]
        return cls(
            vault_root=vault_root,
            index_dir=Path(
                os.environ.get("VAULT_INDEX_DIR", vault_root / DEFAULT_INDEX_DIRNAME)
            ).expanduser(),
            ollama_url=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL),
            embed_model=os.environ.get("VAULT_EMBED_MODEL", DEFAULT_EMBED_MODEL),
            embed_dim=dimensions,
            ignore_dirs=tuple(dict.fromkeys((*DEFAULT_IGNORE_DIRS, *extra_dirs))),
            daily_dir=os.environ.get("VAULT_DAILY_DIR", DEFAULT_DAILY_DIR),
        )
