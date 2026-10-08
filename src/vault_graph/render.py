from __future__ import annotations

import json
from typing import Any


def render(command: str, rows: list[dict], refreshed: int, agent: bool) -> str:
    if agent:
        return json.dumps(
            {
                "meta": {
                    "command": command,
                    "count": len(rows),
                    "refreshed": refreshed,
                },
                "results": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    return _human_table(rows)


def _human_table(rows: list[dict]) -> str:
    if not rows:
        return "Keine Treffer."
    columns = list(rows[0].keys())
    widths = {c: len(c) for c in columns}
    for row in rows:
        for c in columns:
            widths[c] = max(widths[c], len(str(row.get(c, ""))))

    def fmt(values: dict[str, Any]) -> str:
        return "  ".join(str(values.get(c, "")).ljust(widths[c]) for c in columns)

    header = "  ".join(c.ljust(widths[c]) for c in columns)
    sep = "  ".join("-" * widths[c] for c in columns)
    body = "\n".join(fmt(row) for row in rows)
    return f"{header}\n{sep}\n{body}"
