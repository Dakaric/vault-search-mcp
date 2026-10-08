from vault_search.config import Config
from vault_search.selfcheck import (
    WeakMatch,
    _in_scope,
    check_self_retrieval,
    run_selfcheck,
)

_DIM = 8


def test_in_scope_only_top_level_relative_to_prefix():
    scope = ["00 Kontext/", "02 Projekte/"]
    # direkt unter dem Präfix-Ordner → im Scope
    assert _in_scope("00 Kontext/Leistungen.md", scope) is True
    assert _in_scope("02 Projekte/Projekt Alpha.md", scope) is True
    # tieferer Unterordner → draußen (Kontakte-Spitznamen sind Exakt-Trigger)
    assert _in_scope("00 Kontext/Kontakte/Person A.md", scope) is False
    # anderer Ordner → draußen
    assert _in_scope("05 Daily Notes/2026-01-01.md", scope) is False
    # expliziter Unterordner-Präfix macht dessen Top-Level prüfbar
    assert _in_scope("00 Kontext/Kontakte/Person A.md", ["00 Kontext/Kontakte/"]) is True
    # Präfix ohne trailing / wird normalisiert (sonst still leer → falsches „OK")
    assert _in_scope("00 Kontext/Leistungen.md", ["00 Kontext"]) is True
    assert _in_scope("00 Kontext/Kontakte/X.md", ["00 Kontext"]) is False


def _fake_search(hits):
    """hits: Liste von (path, distance), als search-Ergebnis zurückgeben."""
    return lambda vector, k: [{"path": p, "_distance": d} for p, d in hits][:k]


def test_query_that_finds_the_note_returns_none():
    def embed(text):
        return [0.1]

    search = _fake_search([("02 Projekte/Alpha.md", 0.2), ("x.md", 0.5)])
    assert check_self_retrieval("Alpha", "02 Projekte/Alpha.md", embed, search, top_k=3) is None


def test_query_that_misses_the_note_returns_weakmatch():
    """Echte Rang-Schwäche: drei andere Notizen sind näher, Alpha erst auf Notiz-Rang
    4 → nicht in Top-3."""

    def embed(text):
        return [0.1]

    search = _fake_search(
        [("a.md", 0.2), ("b.md", 0.3), ("c.md", 0.4), ("02 Projekte/Alpha.md", 0.7)]
    )
    m = check_self_retrieval("Projektübersicht", "02 Projekte/Alpha.md", embed, search, top_k=3)
    assert m is not None
    assert m.path == "02 Projekte/Alpha.md"
    assert m.query == "Projektübersicht"
    assert m.self_rank == 4  # 1-basiert im dedupten Fetch gefunden
    assert m.self_distance == 0.7
    assert m.top_paths == ["a.md", "b.md", "c.md"]


def test_dedup_note_with_many_chunks_counts_once():
    """Per-Notiz-Dedup: Notiz B belegt Chunk-Rang 1–3, A ist Chunk-Rang 4, aber
    Notiz-Rang 2 → in Top-3 distinct → NICHT schwach. Ohne Dedup wäre A fälschlich
    schwach (paths[:3] = [B, B, B])."""

    def embed(text):
        return [0.1]

    search = _fake_search([("B.md", 0.10), ("B.md", 0.15), ("B.md", 0.20), ("A.md", 0.30)])
    assert check_self_retrieval("A", "A.md", embed, search, top_k=3) is None


def test_optional_threshold_gates_out_far_hits():
    """Opt-in-Gate (Live-Simulation): mit threshold=0.55 zählt Alpha auf Notiz-Rang 2
    bei d=0.70 nicht als gefunden (über der Schwelle) → schwach. OHNE threshold
    (Default) wäre Alpha auf Rang 2 in Top-3 → None."""

    def embed(text):
        return [0.1]

    search = _fake_search([("x.md", 0.20), ("02 Projekte/Alpha.md", 0.70)])
    # Default (kein Gate): Rang 2 zählt → gefunden.
    assert check_self_retrieval("Alpha", "02 Projekte/Alpha.md", embed, search, top_k=3) is None
    # Opt-in-Gate: über 0.55 → schwach.
    m = check_self_retrieval(
        "Alpha", "02 Projekte/Alpha.md", embed, search, top_k=3, threshold=0.55
    )
    assert m is not None
    assert m.self_rank == 2
    assert m.self_distance == 0.70
    assert m.top_paths == ["x.md"]  # nur der Treffer unter der Schwelle


class _FakeEmbedder:
    """Minimal, der Orchestrierungs-Test stubbt check_self_retrieval, die echten
    Embeddings sind egal. Signatur wie OllamaEmbedder (Context-Manager)."""

    def __init__(self, base_url, model, timeout=60.0):
        pass

    def __enter__(self) -> "_FakeEmbedder":
        return self

    def __exit__(self, *e):
        return None

    def embed(self, text: str) -> list[float]:
        return [0.0] * _DIM

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * _DIM for _ in texts]


def test_run_selfcheck_orchestration(tmp_path, monkeypatch):
    """Scope-Filter + Titel-UND-alias-Query-Bau + Ergebnis-Sammlung. check_self_
    retrieval ist gestubbt (Rang-Mathematik oben separat getestet); hier zählt nur,
    WELCHE (path, query) run_selfcheck baut und wie es sammelt."""
    (tmp_path / "02 Projekte").mkdir(parents=True)
    (tmp_path / "02 Projekte" / "Alpha.md").write_text("# Alpha\n\ninhalt\n", encoding="utf-8")
    (tmp_path / "02 Projekte" / "Beta.md").write_text(
        "---\naliases: [b1, b2]\n---\n# Beta\n\ninhalt\n", encoding="utf-8"
    )
    (tmp_path / "05 Daily Notes").mkdir(parents=True)
    (tmp_path / "05 Daily Notes" / "2026-01-01.md").write_text(
        "# Tag\n\nx\n", encoding="utf-8"
    )  # außerhalb Scope

    seen: list[tuple[str, str]] = []

    def fake_check(query, path, embed, search, top_k, threshold=None):
        seen.append((path, query))
        return WeakMatch(path, query, None, None, []) if query == "b2" else None

    monkeypatch.setattr("vault_search.selfcheck.OllamaEmbedder", _FakeEmbedder)
    monkeypatch.setattr("vault_search.selfcheck.check_self_retrieval", fake_check)
    cfg = Config(
        vault_root=tmp_path,
        index_dir=tmp_path / ".vault-index",
        ollama_url="unused",
        embed_model="fake",
        embed_dim=_DIM,
    )

    weak = run_selfcheck(cfg, scope_prefixes=["02 Projekte/"], top_k=3)

    # Daily Note ist außerhalb Scope → nie geprüft.
    assert all(not p.startswith("05 Daily") for p, _ in seen)
    # Titel UND beide aliases von Beta + Alphas Titel werden als Query gebaut.
    assert ("02 Projekte/Beta.md", "Beta") in seen
    assert ("02 Projekte/Beta.md", "b1") in seen
    assert ("02 Projekte/Beta.md", "b2") in seen
    assert ("02 Projekte/Alpha.md", "Alpha") in seen
    # Nur das gestubbte schwache Paar landet im Ergebnis.
    assert {(w.path, w.query) for w in weak} == {("02 Projekte/Beta.md", "b2")}
