import importlib
import io
import json
import sys
from pathlib import PureWindowsPath
from unittest.mock import Mock

import pytest

from tests.test_indexer import FakeEmbedder
from vault_search import config as config_module
from vault_search import indexer
from vault_search.config import Config
from vault_search.selfcheck import _in_scope


def test_config_requires_vault_root(monkeypatch):
    monkeypatch.delenv("VAULT_ROOT", raising=False)
    with pytest.raises(ValueError, match="VAULT_ROOT ist nicht gesetzt"):
        Config.from_env()


def test_ignore_dirs_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("VAULT_IGNORE_DIRS", "06 Archiv, 07 Anhänge,.git,,")
    config = Config.from_env()
    assert config.ignore_dirs == (
        ".obsidian",
        ".trash",
        ".git",
        ".vault-index",
        ".vault-mcp-state",
        ".claude",
        "node_modules",
        ".venv",
        "06 Archiv",
        "07 Anhänge",
    )


def test_index_paths_use_forward_slashes():
    import vault_md

    helper = getattr(vault_md, "rel_posix", None)
    assert callable(helper), "Gemeinsamer Pfadhelfer fehlt"
    assert (
        helper(
            PureWindowsPath("C:/v/Mein Vault/07 Anhänge/Notiz.md"),
            PureWindowsPath("C:/v/Mein Vault"),
        )
        == "07 Anhänge/Notiz.md"
    )


def test_paths_with_spaces_and_umlauts(tmp_path, monkeypatch):
    root = tmp_path / "Mein Vault"
    folder = root / "07 Anhänge"
    folder.mkdir(parents=True)
    (folder / "Notiz.md").write_text("# Notiz\n\nEin Inhalt.", encoding="utf-8")
    monkeypatch.setattr(indexer, "OllamaEmbedder", FakeEmbedder)
    config = Config(root, root / ".vault-index", "unused", "fake", 8)
    assert indexer.reindex(config).indexed == 1
    assert indexer.VaultStore(config.index_dir, 8, "fake").known_mtimes().keys() == {
        "07 Anhänge/Notiz.md"
    }


def test_empty_scope_checks_whole_vault():
    assert _in_scope("Eigene Ordner/Tief/Notiz.md", [])


def test_server_import_needs_no_configuration(monkeypatch):
    monkeypatch.delenv("VAULT_ROOT", raising=False)
    monkeypatch.setattr(
        Config, "from_env", Mock(side_effect=AssertionError("Konfiguration beim Import"))
    )
    module = importlib.import_module("vault_search.server")
    importlib.reload(module)
    assert module.mcp.name == "vault-search"


@pytest.mark.parametrize("entry", ["reindex", "selfcheck", "graph", "server"])
def test_entrypoints_report_config_error_and_utf8(entry, monkeypatch):
    monkeypatch.delenv("VAULT_ROOT", raising=False)
    output = io.StringIO()
    output.reconfigure = Mock()
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(sys, "stderr", output)
    monkeypatch.setattr(sys, "argv", ["command"])
    if entry == "graph":
        from vault_graph.cli import main

        result = main(["stats"])
    elif entry == "server":
        from vault_search.server import main

        result = main()
    else:
        from vault_search import cli

        result = getattr(cli, entry)()
    assert result == 2
    assert "VAULT_ROOT ist nicht gesetzt" in output.getvalue()
    output.reconfigure.assert_called_with(encoding="utf-8")


def test_graph_ignores_configured_folders(tmp_path, monkeypatch, capsys):
    from vault_graph.cli import main

    (tmp_path / "Auslassen").mkdir()
    (tmp_path / "Auslassen" / "Notiz.md").write_text("Inhalt", encoding="utf-8")
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("VAULT_IGNORE_DIRS", "Auslassen")
    assert main(["stats", "--agent"]) == 0
    assert json.loads(capsys.readouterr().out)["results"][0]["notes"] == 0


def test_daily_directory_changes_on_incremental_refresh(tmp_path, monkeypatch):
    from vault_graph.store import GraphStore

    for folder in ("05 Daily Notes", "Tage/Journal"):
        target = tmp_path / folder
        target.mkdir(parents=True)
        (target / "2026-01-01.md").write_text("Tag", encoding="utf-8")
    store = GraphStore(tmp_path / ".vault-index" / "graph.db")
    store.refresh(tmp_path, {".vault-index"})
    monkeypatch.setenv("VAULT_DAILY_DIR", "Tage/Journal")
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    store.refresh(tmp_path, {".vault-index"}, Config.from_env().daily_dir)
    rows = store.conn.execute("SELECT rel_path FROM notes WHERE is_daily=1").fetchall()
    assert [row[0] for row in rows] == ["Tage/Journal/2026-01-01.md"]
    store.close()


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_invalid_vault_cannot_start_indexing(tmp_path, monkeypatch, kind):
    root = tmp_path / "Kein Vault"
    if kind == "file":
        root.write_text("Kein Ordner", encoding="utf-8")
    monkeypatch.setenv("VAULT_ROOT", str(root))
    with pytest.raises(ValueError, match="Vault"):
        Config.from_env()


@pytest.mark.parametrize("dimension", ["ungültig", "0", "-1"])
def test_bad_dimension_is_config_error(tmp_path, monkeypatch, dimension):
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("VAULT_EMBED_DIM", dimension)
    error_type = config_module.ConfigError
    with pytest.raises(error_type, match="VAULT_EMBED_DIM"):
        Config.from_env()


def test_store_handles_quoted_note_names(tmp_path):
    from vault_search.store import Chunk, VaultStore

    store = VaultStore(tmp_path / ".vault-index", 2)
    note_path = 'Projekte/Notiz "A" und Team\'s.md'
    store.replace_note(note_path, [Chunk(note_path, "", 0, 1.0, "Inhalt", [0.1, 0.2])])
    assert store.known_mtimes() == {note_path: 1.0}
    store.delete_note(note_path)
    assert store.count() == 0


def test_dimension_mismatch_keeps_existing_chunks(tmp_path):
    from vault_search.store import Chunk, VaultStore

    folder = tmp_path / ".vault-index"
    store = VaultStore(folder, 2)
    store.replace_note("Notiz.md", [Chunk("Notiz.md", "", 0, 1.0, "Original", [0.1, 0.2])])
    with pytest.raises(ValueError, match="Dimension"):
        store.replace_note("Notiz.md", [Chunk("Notiz.md", "", 0, 2.0, "Neu", [0.1])])
    assert VaultStore(folder, 2).count() == 1
    with pytest.raises(ValueError, match="Dimension"):
        VaultStore(folder, 3)
