from pathlib import Path

from vault_graph.store import SCHEMA_VERSION, GraphStore


def test_store_initializes_schema_and_version(tmp_path: Path):
    store = GraphStore(tmp_path / "graph.db")
    tables = {
        r[0]
        for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"notes", "links", "todos", "tags", "meta"} <= tables
    assert store.schema_version() == SCHEMA_VERSION


def test_store_rebuilds_on_version_mismatch(tmp_path: Path):
    db = tmp_path / "graph.db"
    store = GraphStore(db)
    store.conn.execute("INSERT INTO notes(rel_path, title) VALUES ('x.md','x')")
    store.conn.execute("UPDATE meta SET value='0' WHERE key='schema_version'")
    store.conn.commit()
    store.close()

    store2 = GraphStore(db)  # Mismatch -> Rebuild
    assert store2.schema_version() == SCHEMA_VERSION
    assert store2.conn.execute("SELECT count(*) FROM notes").fetchone()[0] == 0


TECH_IGNORE = {".obsidian", ".git", ".vault-index"}


def test_refresh_indexes_notes_links_todos_tags(vault):
    store = GraphStore(vault / ".vault-index" / "graph.db")
    stats = store.refresh(vault, TECH_IGNORE)

    assert stats["indexed"] == 5
    n = store.conn.execute("SELECT count(*) FROM notes").fetchone()[0]
    assert n == 5

    row = store.conn.execute(
        "SELECT target_rel_path FROM links WHERE target_title='Projekt Beta'"
    ).fetchone()
    assert row[0] == "02 Projekte/Projekt Beta.md"

    row = store.conn.execute(
        "SELECT target_rel_path FROM links WHERE target_title='Gelöschte Notiz'"
    ).fetchone()
    assert row[0] is None

    assert store.conn.execute("SELECT count(*) FROM todos").fetchone()[0] == 3

    tags = {r[0] for r in store.conn.execute("SELECT DISTINCT tag FROM tags")}
    assert {"projekt", "ki", "voice", "ressource"} <= tags


def test_refresh_is_incremental_and_handles_deletion(vault):
    db = vault / ".vault-index" / "graph.db"
    store = GraphStore(db)
    store.refresh(vault, TECH_IGNORE)

    stats = store.refresh(vault, TECH_IGNORE)
    assert stats["indexed"] == 0
    assert stats["skipped"] == 5

    (vault / "02 Projekte" / "Projekt Beta.md").unlink()
    stats = store.refresh(vault, TECH_IGNORE)
    assert stats["deleted"] == 1
    row = store.conn.execute(
        "SELECT target_rel_path FROM links WHERE target_title='Projekt Beta'"
    ).fetchone()
    assert row[0] is None


def test_refresh_resolves_path_style_links(tmp_path):
    (tmp_path / "00 Kontext").mkdir(parents=True)
    (tmp_path / "00 Kontext" / "Stilregeln.md").write_text("---\n---\nStil", encoding="utf-8")
    (tmp_path / "Note.md").write_text(
        "Ref [[00 Kontext/Stilregeln]] plus [[Stilregeln]] plus [[00 Kontext/Stilregeln.md]]",
        encoding="utf-8",
    )
    store = GraphStore(tmp_path / ".vault-index" / "graph.db")
    store.refresh(tmp_path, TECH_IGNORE)
    rows = store.conn.execute(
        "SELECT target_title, target_rel_path FROM links WHERE src_rel_path='Note.md'"
    ).fetchall()
    resolved = {r["target_title"]: r["target_rel_path"] for r in rows}
    assert resolved["00 Kontext/Stilregeln"] == "00 Kontext/Stilregeln.md"
    assert resolved["Stilregeln"] == "00 Kontext/Stilregeln.md"
    assert resolved["00 Kontext/Stilregeln.md"] == "00 Kontext/Stilregeln.md"
