from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def backlinks(conn: sqlite3.Connection, title: str) -> list[dict]:
    return _rows(
        conn,
        "SELECT DISTINCT src_rel_path AS src FROM links WHERE target_title=? ORDER BY src",
        (title,),
    )


def outgoing_links(conn: sqlite3.Connection, title: str) -> list[dict]:
    return _rows(
        conn,
        "SELECT l.target_title, l.target_rel_path FROM links l "
        "JOIN notes n ON n.rel_path = l.src_rel_path "
        "WHERE n.title=? ORDER BY l.target_title",
        (title,),
    )


def orphans(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn,
        "SELECT rel_path FROM notes WHERE rel_path NOT IN "
        "(SELECT target_rel_path FROM links "
        " WHERE target_rel_path IS NOT NULL AND target_rel_path != src_rel_path) "
        "ORDER BY rel_path",
    )


def broken(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn,
        "SELECT src_rel_path AS src, target_title FROM links "
        "WHERE target_rel_path IS NULL ORDER BY src, target_title",
    )


def todos(
    conn: sqlite3.Connection,
    folder: str | None = None,
    note: str | None = None,
) -> list[dict]:
    sql = (
        "SELECT t.rel_path, t.line_no, t.text FROM todos t "
        "JOIN notes n ON n.rel_path = t.rel_path WHERE t.checked=0"
    )
    params: list = []
    if folder:
        sql += " AND n.folder=?"
        params.append(folder)
    if note:
        sql += " AND n.title=?"
        params.append(note)
    sql += " ORDER BY t.rel_path, t.line_no"
    return _rows(conn, sql, tuple(params))


_FM_COLUMNS = {"status", "erstellt", "quelle", "folder", "title"}


def stale(
    conn: sqlite3.Connection,
    days: int,
    now: float,
    folder: str | None = None,
) -> list[dict]:
    cutoff = now - days * 86400
    sql = "SELECT rel_path, status, mtime FROM notes WHERE status='aktiv' AND mtime < ?"
    params: list = [cutoff]
    if folder:
        sql += " AND folder=?"
        params.append(folder)
    sql += " ORDER BY mtime"
    rows = _rows(conn, sql, tuple(params))
    for r in rows:
        r["last_modified"] = datetime.fromtimestamp(r.pop("mtime")).strftime("%Y-%m-%d")
    return rows


def query_frontmatter(conn: sqlite3.Connection, filters: dict) -> list[dict]:
    clauses: list[str] = []
    params: list = []
    for key, value in filters.items():
        if key not in _FM_COLUMNS:
            raise ValueError(f"Unbekanntes Frontmatter-Feld: {key}")
        clauses.append(f"{key}=?")
        params.append(value)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return _rows(
        conn,
        f"SELECT rel_path, status, erstellt, quelle FROM notes{where} ORDER BY rel_path",
        tuple(params),
    )


def tags(conn: sqlite3.Connection, cooccur: bool = False) -> list[dict]:
    if cooccur:
        return _rows(
            conn,
            "SELECT a.tag AS tag_a, b.tag AS tag_b, COUNT(*) AS count "
            "FROM tags a JOIN tags b "
            "ON a.rel_path=b.rel_path AND a.tag < b.tag "
            "GROUP BY a.tag, b.tag ORDER BY count DESC, tag_a, tag_b",
        )
    return _rows(
        conn,
        "SELECT tag, COUNT(DISTINCT rel_path) AS count FROM tags "
        "GROUP BY tag ORDER BY count DESC, tag",
    )


def daily(conn: sqlite3.Connection, gaps: bool = False) -> list[dict]:
    rows = conn.execute("SELECT title FROM notes WHERE is_daily=1 ORDER BY title").fetchall()
    dates: list[date] = []
    for r in rows:
        try:
            dates.append(date.fromisoformat(r["title"]))
        except ValueError:
            continue
    if not gaps:
        return [{"date": d.isoformat()} for d in dates]
    if len(dates) < 2:
        return []
    missing: list[dict] = []
    cur = dates[0] + timedelta(days=1)
    last = dates[-1]
    present = set(dates)
    while cur < last:
        if cur not in present:
            missing.append({"date": cur.isoformat()})
        cur += timedelta(days=1)
    return missing


def stats(conn: sqlite3.Connection) -> dict:
    def one(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    return {
        "notes": one("SELECT COUNT(*) FROM notes"),
        "links": one("SELECT COUNT(*) FROM links"),
        "broken_links": one("SELECT COUNT(*) FROM links WHERE target_rel_path IS NULL"),
        "open_todos": one("SELECT COUNT(*) FROM todos WHERE checked=0"),
        "tags": one("SELECT COUNT(DISTINCT tag) FROM tags"),
        "daily_notes": one("SELECT COUNT(*) FROM notes WHERE is_daily=1"),
    }


def doctor(conn: sqlite3.Connection) -> dict:
    broken_links = conn.execute(
        "SELECT COUNT(*) FROM links WHERE target_rel_path IS NULL"
    ).fetchone()[0]
    fm_broken = [
        r["rel_path"] for r in conn.execute("SELECT rel_path FROM notes WHERE fm_broken=1")
    ]
    collisions = _rows(
        conn,
        "SELECT title, COUNT(*) AS n FROM notes GROUP BY title HAVING n > 1 ORDER BY title",
    )
    return {
        "broken_links": broken_links,
        "fm_broken_notes": fm_broken,
        "title_collisions": collisions,
    }
