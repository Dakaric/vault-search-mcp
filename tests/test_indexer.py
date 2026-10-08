"""Regression-Tests für vault_search.indexer.reindex, Prune-Verhalten.

Das Modul war bislang ungetestet (Ollama/LanceDB-Abhängigkeit), genau deshalb
blieb der --full-Prune-Blindfleck unbemerkt. Der Fake-Embedder spiegelt die
echte OllamaEmbedder-Signatur (Context-Manager + embed/embed_batch), damit der
Test den echten reindex-Pfad trifft statt an einem geschönten Fake vorbei.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vault_search import indexer
from vault_search.config import Config
from vault_search.indexer import extract_title, note_embed_prefix

_DIM = 8


def test_extract_title_prefers_h1():
    body = "Intro line\n# Echter Titel\nmehr text"
    assert extract_title(body, Path("02 Projekte/Datei.md")) == "Echter Titel"


def test_extract_title_falls_back_to_filename():
    assert extract_title("kein heading", Path("02 Projekte/Mein Projekt.md")) == "Mein Projekt"


def test_note_embed_prefix_joins_title_and_tags_only():
    # aliases bewusst NICHT im Präfix, sonst wird der Self-Check zirkulär.
    meta = {"aliases": ["KI-Berater"], "tags": ["kontext", "leistung"]}
    assert note_embed_prefix("Meine Leistungen", meta) == "Meine Leistungen · kontext, leistung"


def test_note_embed_prefix_normalizes_scalar_tags_and_omits_empty():
    assert note_embed_prefix("Alpha", {"tags": "projekt"}) == "Alpha · projekt"
    assert note_embed_prefix("Nur Titel", {}) == "Nur Titel"


class FakeEmbedder:
    """Deterministische Dummy-Vektoren statt Ollama, Signatur wie OllamaEmbedder."""

    def __init__(self, base_url: str, model: str, timeout: float = 60.0) -> None:
        self._dim = _DIM

    def __enter__(self) -> FakeEmbedder:
        return self

    def __exit__(self, *exc_info) -> None:
        return None

    def embed(self, text: str) -> list[float]:
        seed = float(sum(ord(c) for c in text) % 97)
        return [seed] * self._dim

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


@pytest.fixture
def config(vault) -> Config:
    return Config(
        vault_root=vault,
        index_dir=vault / ".vault-index",
        ollama_url="unused",
        embed_model="fake",
        embed_dim=_DIM,
    )


def test_full_reindex_prunes_orphaned_notes(vault, config, monkeypatch):
    """--full muss verwaiste Notizen prunen, nicht nur upserten.

    Regression: `known = {} if not incremental` ließ die Delete-Schleife bei
    --full leerlaufen, verwaiste Chunks (gelöschte oder neu ignorierte Notizen)
    blieben als Waisen im Index und tauchten als Fehltreffer auf.
    """
    monkeypatch.setattr(indexer, "OllamaEmbedder", FakeEmbedder)

    first = indexer.reindex(config, incremental=False)
    assert first.indexed == 5
    assert first.deleted == 0

    (vault / "04 Ressourcen" / "Orphan.md").unlink()

    second = indexer.reindex(config, incremental=False)
    assert second.deleted == 1, "Voll-Reindex muss die entfernte Notiz prunen"


def test_incremental_reindex_still_skips_and_prunes(vault, config, monkeypatch):
    """Der Fix darf das inkrementelle Verhalten nicht verändern:
    unveränderte Dateien werden geskippt, gelöschte geprunt."""
    monkeypatch.setattr(indexer, "OllamaEmbedder", FakeEmbedder)

    indexer.reindex(config, incremental=False)
    again = indexer.reindex(config, incremental=True)
    assert again.indexed == 0
    assert again.skipped == 5

    (vault / "04 Ressourcen" / "Orphan.md").unlink()
    after = indexer.reindex(config, incremental=True)
    assert after.deleted == 1


def test_build_chunks_prefixes_embed_input_not_stored_text(vault):
    from vault_search.indexer import build_chunks

    captured: list[str] = []

    class RecordingEmbedder:
        def embed_batch(self, texts):
            captured.extend(texts)
            return [[0.0] * _DIM for _ in texts]

    note = vault / "02 Projekte" / "Projekt Alpha.md"
    note.write_text(
        "---\naliases: [Beispielsystem]\ntags: [projekt, ki]\n---\n"
        "# Projekt Alpha\n\n## Stack\n\nDienst A, Dienst B.\n",
        encoding="utf-8",
    )
    chunks = build_chunks(vault, note, RecordingEmbedder())

    # Präfix (Titel + tags, KEINE aliases) steckt im Embed-Input …
    assert any(t.startswith("Projekt Alpha · projekt, ki") for t in captured)
    # … aber NICHT im gespeicherten Chunk-Text.
    assert all("· projekt, ki" not in c.text for c in chunks)
    # der alias steht NICHT im Präfix-Teil (erster Absatz vor dem ersten \n\n)
    assert all("Beispielsystem" not in t.split("\n\n")[0] for t in captured)
    assert any("Dienst A" in c.text for c in chunks)
