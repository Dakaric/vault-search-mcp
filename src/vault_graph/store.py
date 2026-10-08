from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from vault_md import rel_posix
from vault_md.walk import (
    extract_inline_tags,
    extract_todos,
    extract_wikilinks,
    iter_markdown_files,
    read_note,
)
from vault_search.config import DEFAULT_DAILY_DIR

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE notes(
    rel_path TEXT PRIMARY KEY,
    title TEXT,
    folder TEXT,
    mtime REAL,
    status TEXT,
    erstellt TEXT,
    quelle TEXT,
    frontmatter_json TEXT,
    is_daily INTEGER,
    fm_broken INTEGER DEFAULT 0
);
CREATE TABLE links(
    src_rel_path TEXT,
    target_title TEXT,
    target_rel_path TEXT
);
CREATE TABLE todos(
    rel_path TEXT,
    line_no INTEGER,
    text TEXT,
    checked INTEGER
);
CREATE TABLE tags(
    rel_path TEXT,
    tag TEXT,
    source TEXT
);
CREATE TABLE meta(
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX idx_notes_title ON notes(title);
CREATE INDEX idx_links_target ON links(target_title);
CREATE INDEX idx_links_src ON links(src_rel_path);
CREATE INDEX idx_tags_tag ON tags(tag);
CREATE INDEX idx_todos_rel ON todos(rel_path);
"""


class GraphStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _table_exists(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    def schema_version(self) -> int:
        if not self._table_exists("meta"):
            return 0
        row = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row[0]) if row else 0

    def _ensure_schema(self) -> None:
        if self.schema_version() != SCHEMA_VERSION:
            self._rebuild()

    def _rebuild(self) -> None:
        for name in ("notes", "links", "todos", "tags", "meta"):
            self.conn.execute(f"DROP TABLE IF EXISTS {name}")
        self.conn.executescript(_SCHEMA)
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def known_mtimes(self) -> dict[str, float]:
        return {
            r["rel_path"]: r["mtime"]
            for r in self.conn.execute("SELECT rel_path, mtime FROM notes")
        }

    def _delete_note_rows(self, rel: str) -> None:
        for tbl in ("notes", "todos", "tags"):
            self.conn.execute(f"DELETE FROM {tbl} WHERE rel_path=?", (rel,))
        self.conn.execute("DELETE FROM links WHERE src_rel_path=?", (rel,))

    def _insert_note(self, path, rel: str) -> None:
        body, meta = read_note(path)
        meta = meta if isinstance(meta, dict) else {}
        # v1: read_note schluckt Parse-Fehler und liefert {}; broken vs. leeres
        # Frontmatter ist hier nicht unterscheidbar. fm_broken bleibt 0 (v2-Signal).
        fm_broken = 0
        title = path.stem
        folder = rel.split("/", 1)[0] if "/" in rel else ""
        is_daily = 0
        self.conn.execute(
            "INSERT INTO notes(rel_path,title,folder,mtime,status,erstellt,quelle,"
            "frontmatter_json,is_daily,fm_broken) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                rel,
                title,
                folder,
                path.stat().st_mtime,
                str(meta.get("status")) if meta.get("status") is not None else None,
                str(meta.get("erstellt")) if meta.get("erstellt") is not None else None,
                str(meta.get("quelle")) if meta.get("quelle") is not None else None,
                json.dumps(meta, default=str, ensure_ascii=False),
                is_daily,
                fm_broken,
            ),
        )
        for target in extract_wikilinks(body):
            self.conn.execute(
                "INSERT INTO links(src_rel_path,target_title,target_rel_path) VALUES (?,?,NULL)",
                (rel, target),
            )
        for line_no, text, checked in extract_todos(body):
            self.conn.execute(
                "INSERT INTO todos(rel_path,line_no,text,checked) VALUES (?,?,?,?)",
                (rel, line_no, text, 1 if checked else 0),
            )
        fm_tags = meta.get("tags") or []
        if isinstance(fm_tags, str):
            fm_tags = [fm_tags]
        for tag in fm_tags:
            self.conn.execute(
                "INSERT INTO tags(rel_path,tag,source) VALUES (?,?, 'frontmatter')",
                (rel, str(tag)),
            )
        for tag in extract_inline_tags(body):
            self.conn.execute(
                "INSERT INTO tags(rel_path,tag,source) VALUES (?,?, 'inline')",
                (rel, tag),
            )

    def _resolve_links(self) -> None:
        # Obsidian-Links gibt es als reinen Titel ([[Note]]) und als Pfad
        # ([[Ordner/Note]], optional mit .md). Beide Formen auflösen.
        by_relkey: dict[str, str] = {}
        by_title: dict[str, list[str]] = {}
        for r in self.conn.execute("SELECT rel_path, title FROM notes"):
            rel = r["rel_path"]
            relkey = rel[:-3] if rel.endswith(".md") else rel
            by_relkey[relkey] = rel
            by_title.setdefault(r["title"], []).append(rel)

        def pick(paths: list[str]) -> str:
            return sorted(paths, key=lambda p: (p.count("/"), p))[0]

        def resolve(target: str) -> str | None:
            key = target[:-3] if target.endswith(".md") else target
            if key in by_relkey:
                return by_relkey[key]
            base = key.rsplit("/", 1)[-1]
            paths = by_title.get(base)
            return pick(paths) if paths else None

        for r in self.conn.execute("SELECT rowid, target_title FROM links").fetchall():
            resolved = resolve(r["target_title"])
            self.conn.execute(
                "UPDATE links SET target_rel_path=? WHERE rowid=?",
                (resolved, r["rowid"]),
            )

    def refresh(
        self, vault_root, ignored_dirs: set[str], daily_dir: str = DEFAULT_DAILY_DIR
    ) -> dict[str, int]:
        stats = {"scanned": 0, "indexed": 0, "skipped": 0, "deleted": 0}
        known = self.known_mtimes()
        seen: set[str] = set()
        for path in iter_markdown_files(vault_root, ignored_dirs):
            stats["scanned"] += 1
            rel = rel_posix(path, vault_root)
            seen.add(rel)
            if known.get(rel) == path.stat().st_mtime:
                stats["skipped"] += 1
                continue
            self._delete_note_rows(rel)
            self._insert_note(path, rel)
            stats["indexed"] += 1
        for rel in known:
            if rel not in seen:
                self._delete_note_rows(rel)
                stats["deleted"] += 1
        # Link-Auflösung nur, wenn sich die Notizmenge geändert hat, sonst
        # ist die title→path-Map unverändert und ein Full-Update wäre Arbeit
        # für nichts (Performance).
        if stats["indexed"] or stats["deleted"]:
            self._resolve_links()
        self._refresh_daily_flags(vault_root, daily_dir)
        self.conn.commit()
        return stats

    def _refresh_daily_flags(self, vault_root: Path, daily_dir: str) -> None:
        daily_dir = daily_dir.strip("/")
        folder = Path(daily_dir)
        valid = bool(daily_dir) and not folder.is_absolute() and ".." not in folder.parts
        exists = valid and (vault_root / folder).is_dir()
        prefix = folder.as_posix() + "/"
        self.conn.execute("UPDATE notes SET is_daily=0")
        if exists:
            self.conn.execute(
                "UPDATE notes SET is_daily=1 WHERE substr(rel_path, 1, ?)=?",
                (len(prefix), prefix),
            )

    def close(self) -> None:
        self.conn.close()
