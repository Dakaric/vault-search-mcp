from __future__ import annotations

import os
import re
from collections.abc import Collection, Iterator
from pathlib import Path

import frontmatter

_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


def iter_markdown_files(vault_root: Path, ignored_dirs: Collection[str]) -> Iterator[Path]:
    if not vault_root.is_dir():
        raise ValueError(f"Vault ist kein erreichbarer Ordner: {vault_root}")

    def report_error(error: OSError) -> None:
        # Ein unvollständiger Scan darf vorhandene Indexeinträge nicht als gelöscht behandeln.
        raise error

    for root, dirs, files in os.walk(vault_root, onerror=report_error):
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        for name in files:
            if name.endswith(".md"):
                yield Path(root) / name


def read_note(path: Path) -> tuple[str, dict]:
    try:
        post = frontmatter.load(path)
        return post.content, post.metadata
    except Exception:
        return path.read_text(encoding="utf-8", errors="replace"), {}


def _strip_code(body: str) -> str:
    body = _FENCED_CODE.sub(" ", body)
    body = _INLINE_CODE.sub(" ", body)
    return body


_INLINE_TAG = re.compile(r"(?:^|(?<=\s))#(\w[\w/-]*)")
_HEX = re.compile(r"^[0-9a-fA-F]{3}$|^[0-9a-fA-F]{6}$")


def extract_inline_tags(body: str) -> list[str]:
    """Distinct Inline-`#tags`. Schließt Headings, Hex-Farben, URL-Anker
    und Code aus."""
    text = _strip_code(body)
    out: list[str] = []
    seen: set[str] = set()
    for tag in _INLINE_TAG.findall(text):
        if _HEX.match(tag) or tag.isdigit():
            # Hex-Farben und rein numerische Tokens (#2024) sind keine Tags;
            # Obsidian verlangt mindestens ein nicht-numerisches Zeichen.
            continue
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def extract_wikilinks(body: str) -> list[str]:
    """Distinct Link-Ziele in Auftreten-Reihenfolge. Alias (`|`) und
    Heading-Anker (`#`) werden abgeschnitten; Code wird ignoriert."""
    text = _strip_code(body)
    out: list[str] = []
    seen: set[str] = set()
    for raw in _WIKILINK.findall(text):
        target = raw.split("|", 1)[0].split("#", 1)[0].strip()
        if target and target not in seen:
            seen.add(target)
            out.append(target)
    return out


_TODO = re.compile(r"^\s*- \[([ xX])\]\s+(.*\S)\s*$")


def extract_todos(body: str) -> list[tuple[int, str, bool]]:
    """(Zeilennummer 1-basiert, Text, checked) je Checkbox-Zeile."""
    out: list[tuple[int, str, bool]] = []
    for i, line in enumerate(body.splitlines(), start=1):
        m = _TODO.match(line)
        if m:
            out.append((i, m.group(2), m.group(1).lower() == "x"))
    return out
