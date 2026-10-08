from pathlib import Path

import pytest


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Mini-Vault mit bekannten Kanten, Orphan, broken Link, TODOs, Tags, Daily."""

    def w(rel: str, text: str) -> None:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    w(
        "02 Projekte/Projekt Alpha.md",
        "---\nstatus: aktiv\ntags: [projekt, ki]\nerstellt: 2026-01-01\n---\n"
        "Siehe [[Projekt Beta]] und #voice.\n- [ ] Prompt finalisieren\n",
    )
    w(
        "02 Projekte/Projekt Beta.md",
        "---\nstatus: aktiv\n---\nBezug zu [[Projekt Alpha]] und [[Gelöschte Notiz]].\n"
        "- [ ] OCR prüfen\n- [x] Setup\n",
    )
    w("04 Ressourcen/Orphan.md", "---\ntags: [ressource]\n---\nNiemand verlinkt mich. #ki\n")
    w("05 Daily Notes/2026-05-30.md", "---\n---\nTaglog\n")
    w("05 Daily Notes/2026-06-01.md", "---\n---\nTaglog\n")
    return tmp_path


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    import os
    import socket

    for name in tuple(os.environ):
        if name.startswith("VAULT_") or name == "OLLAMA_URL":
            monkeypatch.delenv(name)

    def refuse_network(*args, **kwargs):
        raise AssertionError("Netzaufrufe sind in Tests verboten")

    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket, "create_connection", refuse_network)
