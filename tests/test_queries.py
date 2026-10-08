import os
import time

from vault_graph import queries
from vault_graph.store import GraphStore

TECH_IGNORE = {".obsidian", ".git", ".vault-index"}


def _store(vault):
    s = GraphStore(vault / ".vault-index" / "graph.db")
    s.refresh(vault, TECH_IGNORE)
    return s


def test_backlinks(vault):
    s = _store(vault)
    rows = queries.backlinks(s.conn, "Projekt Alpha")
    assert [r["src"] for r in rows] == ["02 Projekte/Projekt Beta.md"]


def test_outgoing_links(vault):
    s = _store(vault)
    rows = queries.outgoing_links(s.conn, "Projekt Beta")
    targets = sorted(r["target_title"] for r in rows)
    assert targets == ["Gelöschte Notiz", "Projekt Alpha"]


def test_orphans(vault):
    s = _store(vault)
    orphans = {r["rel_path"] for r in queries.orphans(s.conn)}
    assert "04 Ressourcen/Orphan.md" in orphans
    assert "02 Projekte/Projekt Alpha.md" not in orphans


def test_broken(vault):
    s = _store(vault)
    rows = queries.broken(s.conn)
    assert any(
        r["target_title"] == "Gelöschte Notiz" and r["src"] == "02 Projekte/Projekt Beta.md"
        for r in rows
    )


def test_todos_open_only_with_folder_filter(vault):
    s = _store(vault)
    rows = queries.todos(s.conn, folder="02 Projekte", note=None)
    texts = sorted(r["text"] for r in rows)
    assert texts == ["OCR prüfen", "Prompt finalisieren"]
    assert all(r["rel_path"].startswith("02 Projekte/") for r in rows)


def test_stale_active_notes_older_than_days(vault):
    old = time.time() - 40 * 86400
    os.utime(vault / "02 Projekte" / "Projekt Alpha.md", (old, old))
    s = _store(vault)
    rows = queries.stale(s.conn, days=30, now=time.time())
    rels = {r["rel_path"] for r in rows}
    assert "02 Projekte/Projekt Alpha.md" in rels
    assert "02 Projekte/Projekt Beta.md" not in rels


def test_query_frontmatter_status_and_folder(vault):
    s = _store(vault)
    rows = queries.query_frontmatter(s.conn, {"status": "aktiv", "folder": "02 Projekte"})
    rels = sorted(r["rel_path"] for r in rows)
    assert rels == [
        "02 Projekte/Projekt Alpha.md",
        "02 Projekte/Projekt Beta.md",
    ]


def test_tags_frequency(vault):
    s = _store(vault)
    rows = queries.tags(s.conn)
    freq = {r["tag"]: r["count"] for r in rows}
    assert freq["ki"] == 2
    assert freq["projekt"] == 1


def test_daily_gaps(vault):
    s = _store(vault)
    gaps = queries.daily(s.conn, gaps=True)
    missing = {r["date"] for r in gaps}
    assert "2026-05-31" in missing


def test_stats_counts(vault):
    s = _store(vault)
    st = queries.stats(s.conn)
    assert st["notes"] == 5
    assert st["links"] == 3
    assert st["broken_links"] == 1
    assert st["open_todos"] == 2


def test_doctor_reports_broken_links(vault):
    s = _store(vault)
    report = queries.doctor(s.conn)
    assert report["broken_links"] == 1
    assert isinstance(report["fm_broken_notes"], list)


def test_orphans_self_link_does_not_count(tmp_path):
    (tmp_path / "Solo.md").write_text("Ich [[Solo]] verlinke nur mich selbst.", encoding="utf-8")
    s = GraphStore(tmp_path / ".vault-index" / "graph.db")
    s.refresh(tmp_path, TECH_IGNORE)
    orphans = {r["rel_path"] for r in queries.orphans(s.conn)}
    assert "Solo.md" in orphans


def test_stale_human_date_and_folder_filter(vault):
    from datetime import datetime

    old = time.time() - 40 * 86400
    os.utime(vault / "02 Projekte" / "Projekt Alpha.md", (old, old))
    s = _store(vault)
    rows = queries.stale(s.conn, days=30, now=time.time(), folder="02 Projekte")
    assert all(r["rel_path"].startswith("02 Projekte/") for r in rows)
    alpha = next(r for r in rows if r["rel_path"] == "02 Projekte/Projekt Alpha.md")
    assert alpha["last_modified"] == datetime.fromtimestamp(old).strftime("%Y-%m-%d")
    assert "mtime" not in alpha
