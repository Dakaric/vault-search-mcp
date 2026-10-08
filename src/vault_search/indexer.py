from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vault_md import rel_posix
from vault_md.walk import iter_markdown_files, read_note

from .chunking import RawChunk, split_by_heading
from .config import Config
from .embeddings import OllamaEmbedder
from .store import Chunk, VaultStore


@dataclass
class IndexStats:
    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    deleted: int = 0
    chunks: int = 0


def extract_title(body: str, path: Path) -> str:
    """Notiz-Titel: erste H1-Zeile, sonst Dateiname ohne Endung."""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return path.stem


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


def note_embed_prefix(title: str, meta: dict) -> str:
    """`Titel · tag1, tag2`, leere Teile weggelassen. Bewusst OHNE aliases:
    stünden die aliases im Präfix, fände der Self-Retrieval-Check jede Notiz
    trivial unter ihren eigenen aliases (zirkulär). Suchsynonyme gehören in den
    Definitions-Lead (Content). Wandert nur in den Embed-Input, nie in den
    gespeicherten Chunk-Text."""
    parts = [title]
    tags = _as_list(meta.get("tags"))
    if tags:
        parts.append(", ".join(tags))
    return " · ".join(parts)


def build_chunks(
    vault_root: Path,
    path: Path,
    embedder: OllamaEmbedder,
) -> list[Chunk]:
    body, meta = read_note(path)
    if not body.strip():
        return []
    rel = rel_posix(path, vault_root)
    mtime = path.stat().st_mtime
    raw: list[RawChunk] = split_by_heading(body)
    if not raw:
        return []
    prefix = note_embed_prefix(extract_title(body, path), meta)
    texts = [
        f"{prefix}\n\n{chunk.heading}\n\n{chunk.text}"
        if chunk.heading
        else f"{prefix}\n\n{chunk.text}"
        for chunk in raw
    ]
    vectors = embedder.embed_batch(texts)
    return [
        Chunk(
            path=rel,
            heading=chunk.heading,
            chunk_idx=idx,
            mtime=mtime,
            text=chunk.text,
            vector=vector,
        )
        for idx, (chunk, vector) in enumerate(zip(raw, vectors, strict=True))
    ]


def reindex(config: Config, incremental: bool = True) -> IndexStats:
    if not config.vault_root.is_dir():
        raise ValueError(f"Vault ist kein erreichbarer Ordner: {config.vault_root}")
    store = VaultStore(
        config.index_dir, config.embed_dim, config.embed_model, full=not incremental
    )
    stats = IndexStats()
    # Immer laden: known ist die Prune-Basis (verwaiste/ignorierte Notizen aus
    # dem Store entfernen). Das incremental-Flag steuert nur den Skip unten,
    # NICHT das Prunen, sonst lässt --full die Delete-Schleife leerlaufen.
    known = store.known_mtimes()

    with OllamaEmbedder(config.ollama_url, config.embed_model) as embedder:
        seen: set[str] = set()
        for path in iter_markdown_files(config.vault_root, config.ignore_dirs):
            stats.scanned += 1
            rel = rel_posix(path, config.vault_root)
            seen.add(rel)
            current_mtime = path.stat().st_mtime
            if incremental and known.get(rel) == current_mtime:
                stats.skipped += 1
                continue
            chunks = build_chunks(config.vault_root, path, embedder)
            written = store.replace_note(rel, chunks)
            stats.indexed += 1
            stats.chunks += written

        for rel in list(known.keys()):
            if rel not in seen:
                store.delete_note(rel)
                stats.deleted += 1

    return stats
