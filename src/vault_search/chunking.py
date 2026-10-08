from __future__ import annotations

import re
from dataclasses import dataclass

HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
MAX_CHUNK_CHARS = 1200
MIN_CHUNK_CHARS = 80


@dataclass
class RawChunk:
    heading: str
    text: str


def split_by_heading(markdown: str) -> list[RawChunk]:
    lines = markdown.splitlines()
    sections: list[RawChunk] = []
    current_heading = ""
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(buffer).strip()
        if body:
            sections.append(RawChunk(heading=current_heading, text=body))

    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            flush()
            current_heading = m.group(2).strip()
            buffer = []
            continue
        buffer.append(line)
    flush()

    return _split_oversized(sections)


def _split_oversized(sections: list[RawChunk]) -> list[RawChunk]:
    result: list[RawChunk] = []
    for section in sections:
        if len(section.text) <= MAX_CHUNK_CHARS:
            if len(section.text) >= MIN_CHUNK_CHARS or not result:
                result.append(section)
            else:
                result[-1] = RawChunk(
                    heading=result[-1].heading,
                    text=f"{result[-1].text}\n\n{section.text}",
                )
            continue
        for piece in _paragraph_windows(section.text, MAX_CHUNK_CHARS):
            result.append(RawChunk(heading=section.heading, text=piece))
    return result


def _paragraph_windows(text: str, max_chars: int) -> list[str]:
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        paragraphs.extend(_hard_split(block, max_chars))

    windows: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
            continue
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}"
        else:
            windows.append(current)
            current = para
    if current:
        windows.append(current)
    return windows


def _hard_split(block: str, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]
    pieces: list[str] = []
    start = 0
    while start < len(block):
        end = min(start + max_chars, len(block))
        pieces.append(block[start:end].strip())
        start = end
    return [p for p in pieces if p]
