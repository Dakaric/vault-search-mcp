"""Prüft, ob Titel und Aliasse die eigene Notiz unter den besten Treffern finden.

Der Rang zählt unterschiedliche Notizen. Ein optionaler Distanzgrenzwert
filtert zusätzlich; kurze Titel brauchen oft andere Grenzen als ganze Fragen.
Aliasse fehlen bewusst im Embedding-Präfix, damit die Prüfung aussagekräftig bleibt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from vault_md import rel_posix
from vault_md.walk import iter_markdown_files, read_note

from .config import Config
from .embeddings import OllamaEmbedder
from .indexer import _as_list, extract_title
from .store import VaultStore

_FETCH = 15  # größer als top_k, damit der eigene Rang für den Report sichtbar wird

# Optionaler Richtwert, weil geeignete Distanzen vom Modell und den Fragen abhängen.
DEFAULT_THRESHOLD = 0.55


@dataclass(frozen=True)
class WeakMatch:
    path: str
    query: str  # Suchbegriff (Titel oder alias), der NICHT zur Notiz führt
    self_rank: int | None  # 1-basierter Notiz-Rang im Fetch, None wenn nicht gefunden
    self_distance: float | None
    top_paths: list[str]  # distinct Notizen, die stattdessen oben stehen


def check_self_retrieval(
    query: str,
    path: str,
    embed: Callable[[str], list[float]],
    search: Callable[[list[float], int], list[dict]],
    top_k: int,
    threshold: float | None = None,
) -> WeakMatch | None:
    """None, wenn die Query die Notiz unter den top_k distinct Notizen findet, sonst
    eine WeakMatch. `threshold=None` = reiner Notiz-Rang (Default, s. Modul-Doc);
    ein Wert filtert zusätzlich Treffer über der Distanz-Schwelle (Live-Simulation)."""
    vector = embed(query)
    rows = search(vector, max(top_k, _FETCH))
    # Per-Notiz-Dedup wie der produktive Retriever: min-Distanz pro Notiz, damit
    # eine Notiz mit vielen matchenden Chunks nicht mehrere Top-Slots belegt.
    best: dict[str, float] = {}
    for row in rows:
        p = row.get("path")
        d = row.get("_distance")
        if p is None or d is None:
            continue
        if p not in best or d < best[p]:
            best[p] = d
    ranked = sorted(best.items(), key=lambda kv: kv[1])  # [(path, dist), …] distinct, nah→fern
    # threshold=None → alle distinct Notizen zählen (reiner Rang); ein Wert gated
    # zusätzlich auf die Live-Schwelle.
    eligible = [p for p, d in ranked if threshold is None or d <= threshold]
    top_paths = eligible[:top_k]
    if path in top_paths:
        return None
    # Report: Notiz-Rang/-Distanz in der dedupten Liste (auch über der Schwelle,
    # so wird sichtbar, wie nah die Notiz kommt, wenn eine andere sie verdrängt).
    self_rank = None
    self_distance = None
    for idx, (p, d) in enumerate(ranked, start=1):
        if p == path:
            self_rank = idx
            self_distance = d
            break
    return WeakMatch(
        path=path,
        query=query,
        self_rank=self_rank,
        self_distance=self_distance,
        top_paths=top_paths,
    )


def _in_scope(rel: str, scope_prefixes: list[str]) -> bool:
    """Leere Auswahl prüft alles, sonst nur direkt unter den gewählten Ordnern."""
    if not scope_prefixes:
        return True
    for prefix in scope_prefixes:
        if not prefix:
            continue
        norm = prefix if prefix.endswith("/") else prefix + "/"
        if rel.startswith(norm) and "/" not in rel[len(norm) :]:
            return True
    return False


def run_selfcheck(
    config: Config,
    scope_prefixes: list[str],
    top_k: int = 3,
    threshold: float | None = None,
) -> list[WeakMatch]:
    """Prüft je Notiz (unter scope_prefixes) den Titel UND jeden alias als Query.
    Eine (Notiz, Query) landet in der Liste, wenn die Query die Notiz nicht unter
    den top_k distinct Notizen findet. `threshold` opt-in wie check_self_retrieval."""
    store = VaultStore(config.index_dir, config.embed_dim, config.embed_model)
    weak: list[WeakMatch] = []
    with OllamaEmbedder(config.ollama_url, config.embed_model) as embedder:
        for path in iter_markdown_files(config.vault_root, config.ignore_dirs):
            rel = rel_posix(path, config.vault_root)
            if not _in_scope(rel, scope_prefixes):
                continue
            body, meta = read_note(path)
            queries = [extract_title(body, path)] + _as_list(meta.get("aliases"))
            for query in queries:
                result = check_self_retrieval(
                    query, rel, embedder.embed, store.search, top_k, threshold
                )
                if result is not None:
                    weak.append(result)
    return weak
