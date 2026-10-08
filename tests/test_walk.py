from pathlib import Path

from vault_md.walk import (
    extract_inline_tags,
    extract_todos,
    extract_wikilinks,
    iter_markdown_files,
    read_note,
)


def test_extract_wikilinks_basic_alias_heading_dedup():
    body = (
        "Siehe [[Projekt Alpha]] und [[Projekt X|der Alias]] sowie "
        "[[Notiz#Abschnitt]]. Nochmal [[Projekt Alpha]].\n"
        "Code bleibt außen vor: `[[Nicht Dieser]]`\n"
        "```\n[[Auch Nicht]]\n```\n"
    )
    assert extract_wikilinks(body) == ["Projekt Alpha", "Projekt X", "Notiz"]


def test_extract_inline_tags_excludes_headings_hex_urls():
    body = (
        "Ein #ki und #3d-druck Tag, plus #projekt/alpha.\n"
        "## Überschrift ist kein Tag\n"
        "Hex #fff und #ffffff sind keine Tags.\n"
        "URL https://x.de/seite#anchor auch nicht.\n"
        "Inline-Code `#nocode` raus, ```\n#nofence\n``` raus.\n"
    )
    assert extract_inline_tags(body) == ["ki", "3d-druck", "projekt/alpha"]


def test_extract_inline_tags_excludes_pure_numeric():
    assert extract_inline_tags("Jahr #2024 aber #q4 zählt") == ["q4"]


def test_extract_todos_open_and_checked_with_linenumbers():
    body = (
        "# Titel\n"
        "- [ ] offenes todo\n"
        "Text\n"
        "  - [x] erledigt mit Einrückung\n"
        "- [] kein gültiges Format\n"
    )
    assert extract_todos(body) == [
        (2, "offenes todo", False),
        (4, "erledigt mit Einrückung", True),
    ]


def test_iter_markdown_files_respects_ignored_dirs(tmp_path: Path):
    (tmp_path / "a.md").write_text("---\ntags: [x]\n---\nA", encoding="utf-8")
    skip = tmp_path / "06 Archiv"
    skip.mkdir()
    (skip / "old.md").write_text("alt", encoding="utf-8")
    keep = tmp_path / "02 Projekte"
    keep.mkdir()
    (keep / "p.md").write_text("P", encoding="utf-8")

    found = {
        p.relative_to(tmp_path).as_posix()
        for p in iter_markdown_files(tmp_path, ignored_dirs={"06 Archiv"})
    }
    assert found == {"a.md", "02 Projekte/p.md"}


def test_read_note_returns_body_and_frontmatter(tmp_path: Path):
    note = tmp_path / "n.md"
    note.write_text("---\nstatus: aktiv\n---\nInhalt hier", encoding="utf-8")
    body, meta = read_note(note)
    assert body.strip() == "Inhalt hier"
    assert meta["status"] == "aktiv"


def test_walk_does_not_hide_directory_access_errors(tmp_path, monkeypatch):
    import os

    def denied_walk(root, **kwargs):
        error = PermissionError("Ordner nicht lesbar")
        if "onerror" in kwargs:
            kwargs["onerror"](error)
        return iter(())

    monkeypatch.setattr(os, "walk", denied_walk)
    import pytest

    with pytest.raises(PermissionError):
        list(iter_markdown_files(tmp_path, set()))
