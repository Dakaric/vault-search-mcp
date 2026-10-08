import json

from vault_graph.cli import main

TECH_IGNORE = {".obsidian", ".git", ".vault-index"}


def test_cli_broken_agent(vault, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_ROOT", str(vault))
    monkeypatch.setenv("VAULT_INDEX_DIR", str(vault / ".vault-index"))
    rc = main(["broken", "--agent"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["meta"]["command"] == "broken"
    assert any(r["target_title"] == "Gelöschte Notiz" for r in out["results"])


def test_cli_backlinks_human(vault, monkeypatch, capsys):
    monkeypatch.setenv("VAULT_ROOT", str(vault))
    monkeypatch.setenv("VAULT_INDEX_DIR", str(vault / ".vault-index"))
    rc = main(["backlinks", "Projekt Alpha"])
    assert rc == 0
    assert "Projekt Beta" in capsys.readouterr().out
