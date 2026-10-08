import json

from vault_graph.render import render


def test_render_agent_envelope():
    rows = [{"src": "a.md"}, {"src": "b.md"}]
    out = render("broken", rows, refreshed=2, agent=True)
    parsed = json.loads(out)
    assert parsed["meta"] == {"command": "broken", "count": 2, "refreshed": 2}
    assert parsed["results"] == rows


def test_render_human_table_has_header_and_rows():
    rows = [{"src": "a.md", "target_title": "X"}]
    out = render("broken", rows, refreshed=0, agent=False)
    assert "src" in out and "target_title" in out
    assert "a.md" in out and "X" in out


def test_render_human_empty():
    out = render("orphans", [], refreshed=0, agent=False)
    assert "keine" in out.lower()
