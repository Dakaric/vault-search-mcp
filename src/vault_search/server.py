from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .config import Config
from .embeddings import OllamaEmbedder
from .store import VaultStore

CONFIG: Config
STORE: VaultStore
EMBEDDER: OllamaEmbedder

mcp = FastMCP(
    "vault-search",
    instructions=(
        "Semantische Suche über einen Markdown-Vault. "
        "Gib in `query` natürliche Sprache ein, keine Keyword-Suche. "
        "Liefert Pfad, Überschrift, Textauszug und Score. "
        "score ist eine Distanz: kleiner heißt passender."
    ),
)


class NoteMatch(BaseModel):
    path: str = Field(description="Pfad relativ zum Vault-Root")
    heading: str = Field(description="Überschrift des Chunks")
    chunk_idx: int
    score: float = Field(description="Distanz (kleiner = besser)")
    text: str


def _to_match(row: dict) -> NoteMatch:
    return NoteMatch(
        path=row["path"],
        heading=row.get("heading", ""),
        chunk_idx=row.get("chunk_idx", 0),
        score=float(row.get("_distance", 0.0)),
        text=row.get("text", ""),
    )


@mcp.tool()
def vault_search(query: str, k: int = 5) -> list[NoteMatch]:
    """Semantische Suche über den gesamten Vault. Gibt die k besten Chunks zurück.

    score ist eine Distanz: kleiner heißt passender.
    """
    if not query.strip():
        return []
    vector = EMBEDDER.embed(query)
    return [_to_match(r) for r in STORE.search(vector, k=k)]


@mcp.tool()
def vault_related(note_path: str, k: int = 5) -> list[NoteMatch]:
    """Finde Chunks die thematisch zu einer vorhandenen Notiz passen.

    `note_path` ist der Pfad relativ zum Vault-Root (z.B. '02 Projekte/Suchprojekt.md').
    Nutzt den Durchschnittsvektor aller Chunks der Notiz als Query.
    """
    vectors = STORE.fetch_note_vectors(note_path)
    if not vectors:
        return []
    centroid = [sum(col) / len(col) for col in zip(*vectors, strict=False)]
    matches = STORE.search(centroid, k=k + 20)
    filtered = [m for m in matches if m["path"] != note_path][:k]
    return [_to_match(r) for r in filtered]


@mcp.tool()
def vault_status() -> dict:
    """Metadaten zum Index: Vault-Root, Index-Pfad, Modell, Chunk-Anzahl."""
    return {
        "vault_root": str(CONFIG.vault_root),
        "index_dir": str(CONFIG.index_dir),
        "embed_model": CONFIG.embed_model,
        "embed_dim": CONFIG.embed_dim,
        "ollama_url": CONFIG.ollama_url,
        "chunk_count": STORE.count(),
    }


def main() -> int:
    global CONFIG, STORE, EMBEDDER
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        CONFIG = Config.from_env()
        STORE = VaultStore(CONFIG.index_dir, CONFIG.embed_dim, CONFIG.embed_model)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    with OllamaEmbedder(CONFIG.ollama_url, CONFIG.embed_model) as EMBEDDER:
        mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
