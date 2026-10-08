import ast
import asyncio
import json
import os
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import lancedb
import pytest

from installer import api, shell
from installer.components import index, register
from installer.model import Context
from installer.run import run_components
from tests.test_indexer import FakeEmbedder
from vault_search import indexer
from vault_search.config import Config
from vault_search.store import Chunk, VaultStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def async_runner():
    # Windows braucht socketpair beim Start, vor der Netzwerksperre pro Test.
    with asyncio.Runner() as runner:
        yield runner


def test_search_description_explains_distance(async_runner):
    from vault_search.server import mcp

    sentence = "score ist eine Distanz: kleiner heißt passender"
    tool = next(tool for tool in async_runner.run(mcp.list_tools()) if tool.name == "vault_search")
    assert sentence in tool.description
    assert sentence in mcp.instructions


@pytest.mark.parametrize("host", ["127.0.0.1", "192.0.2.1"])
def test_async_runner_keeps_network_blocked(async_runner, host):
    async def connect():
        with socket.socket() as client:
            client.connect((host, 80))

    with pytest.raises(AssertionError, match="Netzaufrufe"):
        async_runner.run(connect())


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "which", lambda name: "/bin/" + name)
    return Context(
        "linux",
        tmp_path,
        False,
        True,
        {
            "vault": str(tmp_path),
            "model": "mxbai-embed-large",
            "repo": str(ROOT),
        },
    )


def registration_output(scope="User", command="/bin/uv", args=None):
    args = args or "--directory /old repo run vault-search-mcp"
    return (
        f"Scope: {scope} (configuration)\nCommand: {command}\nArgs: {args}\n"
        "Environment:\n  VAULT_ROOT=/old vault\n  VAULT_EMBED_MODEL=old-model\n"
    )


@pytest.mark.parametrize(
    "scope,command,args",
    [
        ("User", "/bin/other", "run vault-search-mcp"),
        ("User", "/bin/uv", "run foreign-server"),
        ("Project", "/bin/uv", None),
        ("Local", "/bin/uv", None),
    ],
)
def test_foreign_registration_never_removed(context, monkeypatch, scope, command, args):
    context.assume_yes = False
    monkeypatch.setattr("builtins.input", lambda _: "j")
    monkeypatch.setattr(
        shell,
        "capture",
        lambda _: subprocess.CompletedProcess([], 0, registration_output(scope, command, args), ""),
    )
    run = Mock()
    monkeypatch.setattr(shell, "run", run)
    result = register.apply(context)
    assert result.status == "handarbeit"
    assert "mcp add vault-search" in result.detail
    run.assert_not_called()


@pytest.mark.parametrize("assume_yes", [True, False])
def test_replacement_defaults_to_no(context, monkeypatch, assume_yes):
    context.assume_yes = assume_yes
    monkeypatch.setattr("builtins.input", lambda _: "")
    monkeypatch.setattr(
        shell, "capture", lambda _: subprocess.CompletedProcess([], 0, registration_output(), "")
    )
    run = Mock()
    monkeypatch.setattr(shell, "run", run)
    assert register.apply(context).status == "handarbeit"
    run.assert_not_called()


def test_failed_add_reports_recovery_command(context, monkeypatch):
    context.assume_yes = False
    monkeypatch.setattr("builtins.input", lambda _: "j")
    monkeypatch.setattr(
        shell, "capture", lambda _: subprocess.CompletedProcess([], 0, registration_output(), "")
    )
    run = Mock(side_effect=[None, subprocess.CalledProcessError(1, ["claude"])])
    monkeypatch.setattr(shell, "run", run)
    result = register.apply(context)
    assert result.status == "fehler"
    assert "Wiederherstellen" in result.detail
    assert "'VAULT_ROOT=/old vault'" in result.detail
    assert "VAULT_EMBED_MODEL=old-model" in result.detail
    assert "--directory '/old repo' run vault-search-mcp" in result.detail
    assert run.call_args_list[0].args[0][-4:] == ["remove", "vault-search", "-s", "user"]


@pytest.mark.parametrize("scope", ["User", "User config"])
def test_owned_registration_can_be_replaced_with_consent(context, monkeypatch, scope):
    context.assume_yes = False
    monkeypatch.setattr("builtins.input", lambda _: "j")
    monkeypatch.setattr(
        shell,
        "capture",
        lambda _: subprocess.CompletedProcess([], 0, registration_output(scope), ""),
    )
    run = Mock()
    monkeypatch.setattr(shell, "run", run)
    assert register.apply(context).status == "erledigt"
    assert run.call_args_list[0].args[0][-4:] == ["remove", "vault-search", "-s", "user"]
    assert run.call_args_list[1].args[0] == register.command(context)


def test_recovery_environment_excludes_command_fields(context, monkeypatch):
    context.assume_yes = False
    monkeypatch.setattr("builtins.input", lambda _: "j")
    output = registration_output(args="--directory /repo=old run vault-search-mcp")
    monkeypatch.setattr(shell, "capture", lambda _: subprocess.CompletedProcess([], 0, output, ""))
    monkeypatch.setattr(
        shell,
        "run",
        Mock(
            side_effect=[
                None,
                subprocess.CalledProcessError(1, ["claude"]),
            ]
        ),
    )
    result = register.apply(context)
    assert "-e 'Args:" not in result.detail
    assert "VAULT_EMBED_MODEL=old-model" in result.detail


def test_failed_remove_does_not_add(context, monkeypatch):
    context.assume_yes = False
    monkeypatch.setattr("builtins.input", lambda _: "j")
    monkeypatch.setattr(
        shell, "capture", lambda _: subprocess.CompletedProcess([], 0, registration_output(), "")
    )
    run = Mock(side_effect=subprocess.CalledProcessError(1, ["claude"]))
    monkeypatch.setattr(shell, "run", run)
    assert run_components([register], context)[0].status == "fehler"
    run.assert_called_once()


def test_legacy_table_requires_explicit_rebuild(tmp_path):
    folder = tmp_path / "index"
    store = VaultStore(folder, 2)
    schema = store._table.schema.remove_metadata()
    connection = lancedb.connect(str(folder))
    connection.drop_table("chunks")
    connection.create_table("chunks", schema=schema)
    with pytest.raises(ValueError, match="vault-reindex --full"):
        VaultStore(folder, 2)
    rebuilt = VaultStore(folder, 2, full=True)
    assert rebuilt._table.schema.metadata[b"embed_model"] == b"mxbai-embed-large"


def test_installer_starts_without_third_party_packages(tmp_path):
    environment = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "src")]))
    result = subprocess.run(
        [sys.executable, "-S", "-m", "installer", "--dry-run", "--yes", "--vault", str(tmp_path)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "Dry-Run" in result.stdout
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("dimensions", [8, 4])
def test_model_change_requires_full_and_preserves_other_data(tmp_path, monkeypatch, dimensions):
    monkeypatch.setattr(indexer, "OllamaEmbedder", FakeEmbedder)
    note = tmp_path / "Notiz.md"
    note.write_text("# Notiz\nInhalt", encoding="utf-8")
    config = Config(tmp_path, tmp_path / ".vault-index", "unused", "old-model", 8)
    indexer.reindex(config)
    sentinel = config.index_dir / "graph.db"
    sentinel.write_bytes(b"unrelated data")
    changed = replace(config, embed_model="new-model", embed_dim=dimensions)
    with pytest.raises(ValueError, match="vault-reindex --full"):
        indexer.reindex(changed)
    assert VaultStore(config.index_dir, 8, "old-model").count() == 1

    class NewEmbedder(FakeEmbedder):
        def __init__(self, *args):
            self._dim = dimensions

    monkeypatch.setattr(indexer, "OllamaEmbedder", NewEmbedder)
    assert indexer.reindex(changed, incremental=False).indexed == 1
    table = lancedb.connect(str(config.index_dir)).open_table("chunks")
    assert table.schema.metadata[b"embed_model"] == b"new-model"
    assert table.schema.metadata[b"embed_dim"] == str(dimensions).encode()
    assert table.schema.field("vector").type.list_size == dimensions
    assert sentinel.read_bytes() == b"unrelated data"
    assert note.read_text(encoding="utf-8") == "# Notiz\nInhalt"
    assert indexer.reindex(changed).skipped == 1


@pytest.mark.parametrize("entry", ["reindex", "server"])
def test_entrypoints_report_store_mismatch(tmp_path, monkeypatch, capsys, entry):
    from vault_search import cli, server

    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["command"])
    failing = Mock(side_effect=ValueError("Bitte vault-reindex --full ausführen."))
    monkeypatch.setattr(cli, "run_reindex", failing)
    monkeypatch.setattr(server, "VaultStore", failing)
    assert (cli.reindex() if entry == "reindex" else server.main()) == 2
    output = capsys.readouterr()
    assert "vault-reindex --full" in output.out + output.err


def test_readme_documents_index_storage_and_uninstall():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for term in (
        ".gitignore",
        "iCloud",
        "Dropbox",
        "OneDrive",
        "Syncthing",
        "außerhalb des Vaults",
        "ein Index pro Rechner",
        "claude mcp remove vault-search -s user",
        "Index-Ordner löschen",
    ):
        assert term in text


@pytest.mark.parametrize("system,machine", [("macos", "x86_64"), ("windows", "ARM64")])
def test_unsupported_platform_skips_index(context, monkeypatch, system, machine):
    context.platform = system
    monkeypatch.setattr("platform.machine", lambda: machine)
    monkeypatch.setattr(index, "is_done", Mock(side_effect=AssertionError("Zu früh")))
    result = run_components([index], context)[0]
    assert result.status == "nicht unterstützt"
    assert "LanceDB" in result.detail and "Wheels" in result.detail


def test_launchers_do_not_resolve_project_dependencies():
    for name in ("install.sh", "install.ps1"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "uv run --no-project" in text


def test_readme_names_supported_architectures():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for term in (
        "macOS (Apple Silicon)",
        "Linux x64 und ARM64",
        "Windows x64",
        "Intel-Mac",
        "Windows on ARM",
        "Wheels",
    ):
        assert term in text


def test_installer_rebuilds_changed_model_without_marker_backups(context, monkeypatch):
    monkeypatch.setattr(
        api,
        "request",
        lambda *args, **kwargs: {
            "models": [{"name": context.values["model"]}],
        },
    )
    run = Mock()
    monkeypatch.setattr(shell, "run", run)
    index.apply(context)
    context.values["model"] = "new-model"
    assert not index.is_done(context)
    assert index.apply(context).status == "erledigt"
    command = run.call_args.args[0]
    assert "--full" in command
    assert "--no-dev" in command
    assert "--no-dev" in register.command(context)
    folder = index.index_directory(context)
    marker = json.loads((folder / "installer.json").read_text(encoding="utf-8"))
    assert marker["model"] == "new-model"
    assert not list(folder.glob("installer.json.sicherung-*"))


def test_marker_update_does_not_make_backup(context, monkeypatch):
    monkeypatch.setattr(
        api,
        "request",
        lambda *args, **kwargs: {
            "models": [{"name": context.values["model"]}],
        },
    )
    monkeypatch.setattr(shell, "run", Mock())
    index.apply(context)
    index.apply(context)
    assert not list(index.index_directory(context).glob("installer.json.sicherung-*"))


def test_daily_directory_is_configured_explicitly(tmp_path, monkeypatch):
    from vault_graph.store import GraphStore

    folder = tmp_path / "Journal"
    folder.mkdir()
    (folder / "2026-01-01.md").write_text("Tag", encoding="utf-8")
    monkeypatch.setenv("VAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("VAULT_DAILY_DIR", "Journal")
    config = Config.from_env()
    monkeypatch.setenv("VAULT_DAILY_DIR", "ignored")
    store = GraphStore(config.index_dir / "graph.db")
    store.refresh(config.vault_root, config.ignore_dirs, config.daily_dir)
    assert store.conn.execute("SELECT is_daily FROM notes").fetchone()[0] == 1
    store.close()


@pytest.mark.parametrize(
    "relative,constant",
    [
        ("installer/components/index.py", "DEFAULT_INDEX_DIRNAME"),
        ("installer/components/index.py", "EMBED_DIMENSIONS"),
        ("installer/cli.py", "DEFAULT_EMBED_MODEL"),
        ("installer/components/model.py", "DEFAULT_EMBED_MODEL"),
        ("installer/components/register.py", "DEFAULT_EMBED_MODEL"),
        ("installer/components/register.py", "DEFAULT_OLLAMA_URL"),
        ("installer/components/register.py", "EMBED_DIMENSIONS"),
        ("installer/api.py", "DEFAULT_OLLAMA_URL"),
    ],
)
def test_installer_imports_shared_defaults(relative, constant):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "vault_search.config"
        and constant in {alias.name for alias in node.names}
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize("operation", ["known_mtimes", "fetch_note_vectors"])
def test_store_reads_only_required_columns(tmp_path, monkeypatch, operation):
    store = VaultStore(tmp_path / "index", 2)
    path = "Team's Notiz.md"
    store.replace_note(
        path, [Chunk(path, "", number, number, "Text", [1.0, 2.0]) for number in range(15)]
    )
    store.replace_note("other.md", [Chunk("other.md", "", 0, 1, "Text", [3.0, 4.0])])
    table = store._table
    query = table.search()
    select = Mock(wraps=query.select)
    monkeypatch.setattr(query, "select", select)
    search = Mock(return_value=query)
    monkeypatch.setattr(table, "search", search)
    monkeypatch.setattr(table, "to_arrow", Mock(side_effect=AssertionError("Vollscan")))
    if operation == "known_mtimes":
        assert store.known_mtimes() == {path: 14, "other.md": 1}
        select.assert_called_once_with(["path", "mtime"])
    else:
        assert store.fetch_note_vectors(path) == [[1.0, 2.0]] * 15
        select.assert_called_once_with(["vector"])
    search.assert_called_once_with()


def test_store_uses_list_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(
        lancedb.db.LanceDBConnection,
        "table_names",
        Mock(side_effect=AssertionError("Veraltete Tabellenabfrage")),
    )
    assert VaultStore(tmp_path / "index", 2).count() == 0


def test_selfcheck_fixture_uses_neutral_query():
    text = (ROOT / "tests/test_selfcheck.py").read_text(encoding="utf-8")
    assert "Voice" + " Agent" not in text
