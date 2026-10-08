import io
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import Mock

import pytest

from installer import api, cli, shell
from installer.components import index, model, ollama, register, vault
from installer.model import Context
from installer.run import run_components


@pytest.fixture
def context(tmp_path):
    root = tmp_path / "Mein Vault"
    root.mkdir()
    return Context(
        "linux",
        tmp_path,
        False,
        True,
        {"vault": str(root), "model": "mxbai-embed-large", "repo": str(tmp_path / "Repo mit Ä")},
    )


def test_missing_prerequisite_is_manual_step(context, monkeypatch):
    monkeypatch.setattr(shell, "which", lambda name: "/opt/bin/uv" if name == "uv" else None)
    result = register.apply(context)
    assert result.status == "handarbeit"
    assert "claude mcp add vault-search" in result.detail
    assert "VAULT_ROOT=" in result.detail
    assert "/opt/bin/uv" in result.detail


def test_register_command_quotes_vault_with_spaces(context, monkeypatch):
    monkeypatch.setattr(shell, "which", lambda name: "/bin/" + name)
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 1 if "get" in cmd else 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    assert register.apply(context).status == "erledigt"
    command = next(cmd for cmd in calls if "add" in cmd)
    assert "VAULT_ROOT=" + context.values["vault"] in command
    assert command[command.index("--") + 1] == "/bin/uv"
    assert command[command.index("--directory") + 1] == context.values["repo"]
    assert "VAULT_EMBED_MODEL=mxbai-embed-large" in command


def test_registration_replaces_other_vault_and_keeps_same_vault(context, monkeypatch):
    context.assume_yes = False
    monkeypatch.setattr("builtins.input", lambda _: "j")
    monkeypatch.setattr(shell, "which", lambda name: "/bin/" + name)
    calls = []
    saved = {"root": str(context.home / "Alter Vault")}

    def run(cmd, **kwargs):
        calls.append(cmd)
        if "get" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                0,
                "Scope: User (configuration)\nCommand: /bin/uv\nArgs: --directory "
                + context.values["repo"]
                + " run --no-dev vault-search-mcp\nEnvironment:\n  VAULT_ROOT="
                + saved["root"]
                + "\n",
                "",
            )
        if "add" in cmd:
            saved["root"] = context.values["vault"]
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    assert not register.is_done(context)
    assert register.apply(context).status == "erledigt"
    assert any(cmd[1:] == ["mcp", "remove", "vault-search", "-s", "user"] for cmd in calls)
    assert register.is_done(context)
    before = len([cmd for cmd in calls if "add" in cmd])
    result = run_components([register], context, None)
    assert result[0].status == "übersprungen"
    assert len([cmd for cmd in calls if "add" in cmd]) == before


def test_windows_manual_command_uses_powershell_quoting(context, monkeypatch):
    context.platform = "windows"
    context.values["vault"] = "C:\\Mein Vault\\Team's Notizen"
    monkeypatch.setattr(
        shell, "which", lambda name: "C:\\Tools mit Ä\\uv.exe" if name == "uv" else None
    )
    result = register.apply(context)
    assert "'VAULT_ROOT=C:\\Mein Vault\\Team''s Notizen'" in result.detail


def test_ollama_down_is_manual_step(context, monkeypatch):
    monkeypatch.setattr(api, "request", Mock(side_effect=api.ApiError("Nicht erreichbar")))
    monkeypatch.setattr(shell, "which", lambda name: "/bin/ollama" if name == "ollama" else None)
    assert not ollama.is_done(context)
    result = ollama.apply(context)
    assert result.status == "handarbeit"
    assert "Ollama starten" in result.detail
    assert model.apply(context).status == "handarbeit"
    assert index.apply(context).status == "handarbeit"


def test_ollama_uses_configured_url(monkeypatch):
    captured = []

    class Response(io.BytesIO):
        pass

    def open_request(request, timeout):
        captured.append((request.full_url, timeout))
        return Response(b'{"version":"1"}')

    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:12345/")
    monkeypatch.setattr("urllib.request.urlopen", open_request)
    assert api.request("/api/version") == {"version": "1"}
    assert captured == [("http://127.0.0.1:12345/api/version", 5)]


@pytest.mark.parametrize("tag", ["mxbai-embed-large", "mxbai-embed-large:latest"])
def test_model_recognizes_latest(context, monkeypatch, tag):
    monkeypatch.setattr(api, "request", lambda *args, **kwargs: {"models": [{"name": tag}]})
    assert model.is_done(context)


def test_model_pull_payload_timeout(context, monkeypatch):
    calls = []

    def request(path, data=None, timeout=5):
        calls.append((path, data, timeout))
        return {"status": "success"}

    monkeypatch.setattr(api, "request", request)
    assert model.apply(context).status == "erledigt"
    assert ("/api/pull", {"model": "mxbai-embed-large", "stream": False}, 1800) in calls


def test_download_failure_is_reported(context, monkeypatch):
    def request(path, **kwargs):
        if path == "/api/version":
            return {"version": "1"}
        raise api.ApiError("Download fehlgeschlagen: Verbindung unterbrochen")

    monkeypatch.setattr(api, "request", request)
    results = run_components([model, vault], context, None)
    assert results[0].status == "fehler"
    assert "Verbindung unterbrochen" in results[0].detail
    assert results[1].status != "fehler"


def test_api_reports_http_and_payload_errors(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", Mock(side_effect=urllib.error.URLError("offline"))
    )
    with pytest.raises(api.ApiError, match="offline"):
        api.request("/api/tags")
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *args, **kwargs: io.BytesIO(b'{"error":"Modell fehlt"}')
    )
    with pytest.raises(api.ApiError, match="Modell fehlt"):
        api.request("/api/pull", data={"model": "unknown"})


def test_winget_has_agreements_and_requires_new_terminal(context, monkeypatch):
    context.platform = "windows"
    monkeypatch.setattr(api, "request", Mock(side_effect=api.ApiError("offline")))
    monkeypatch.setattr(shell, "which", lambda name: "winget" if name == "winget" else None)
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )
    result = ollama.apply(context)
    assert result.status == "handarbeit"
    assert "Neues Terminal öffnen" in result.detail
    assert "--accept-package-agreements" in calls[0]
    assert "--accept-source-agreements" in calls[0]


def test_linux_installer_requires_explicit_consent(context, monkeypatch):
    monkeypatch.setattr(api, "request", Mock(side_effect=api.ApiError("offline")))
    monkeypatch.setattr(
        shell, "which", lambda name: "/bin/" + name if name in ("curl", "sh") else None
    )
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: pytest.fail("Keine automatische Installation")
    )
    result = ollama.apply(context)
    assert result.status == "handarbeit"
    assert "https://ollama.com/download" in result.detail


def test_linux_explicit_consent_downloads_script_in_cache(context, monkeypatch):
    context.assume_yes = False
    monkeypatch.setattr("builtins.input", lambda *args: "j")
    monkeypatch.setattr(api, "request", Mock(side_effect=api.ApiError("offline")))
    monkeypatch.setattr(
        shell, "which", lambda name: "/bin/" + name if name in ("curl", "sh") else None
    )
    calls = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kwargs: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    )
    assert ollama.apply(context).status == "handarbeit"
    assert calls[0][0] == "/bin/curl"
    assert "https://ollama.com/install.sh" in calls[0]
    assert calls[1][0] == "/bin/sh"
    assert str(context.home / ".cache" / "vault-search-mcp") in calls[1][1]


def test_index_propagates_configuration_and_only_marks_success(context, monkeypatch):
    monkeypatch.setattr(
        api, "request", lambda *args, **kwargs: {"models": [{"name": "mxbai-embed-large"}]}
    )
    monkeypatch.setattr(shell, "which", lambda name: "/bin/" + name)
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:12345")
    monkeypatch.setenv("VAULT_IGNORE_DIRS", "06 Archiv")
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", run)
    assert not index.is_done(context)
    assert index.apply(context).status == "erledigt"
    command, options = calls[0]
    assert command[-4:] == ["run", "--no-dev", "vault-reindex", "--full"]
    assert options["env"]["VAULT_ROOT"] == context.values["vault"]
    assert options["env"]["VAULT_EMBED_MODEL"] == "mxbai-embed-large"
    assert options["env"]["VAULT_IGNORE_DIRS"] == "06 Archiv"
    assert index.is_done(context)
    context.values["model"] = "anderes-modell"
    assert not index.is_done(context)


def test_index_failure_not_marked_done(context, monkeypatch):
    monkeypatch.setattr(
        api, "request", lambda *args, **kwargs: {"models": [{"name": "mxbai-embed-large"}]}
    )
    monkeypatch.setattr(shell, "which", lambda name: "/bin/" + name)
    monkeypatch.setattr(
        subprocess, "run", Mock(side_effect=subprocess.CalledProcessError(1, ["uv"]))
    )
    assert run_components([index], context, None)[0].status == "fehler"
    assert not index.is_done(context)


def test_vault_must_exist_and_be_absolute(context):
    context.values["vault"] = "relativ"
    assert vault.apply(context).status == "fehler"
    context.values["vault"] = str(context.home / "fehlt")
    assert vault.apply(context).status == "fehler"


def test_dry_run_never_calls_external_services(context, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: pytest.fail("Kein Unterprozess im Dry-Run")
    )
    monkeypatch.setattr(api, "request", lambda *args, **kwargs: pytest.fail("Kein HTTP im Dry-Run"))
    assert cli.main(["--yes", "--dry-run", "--vault", context.values["vault"]]) == 0
    assert list(Path(context.values["vault"]).iterdir()) == []


@pytest.mark.parametrize(
    ("variable", "old_value", "new_value"),
    [
        ("VAULT_EMBED_MODEL", "old-model", "new-model"),
        ("OLLAMA_URL", "http://localhost:11434", "http://localhost:12345"),
        ("VAULT_INDEX_DIR", "/alter-index", "/neuer-index"),
    ],
)
def test_registration_detects_changed_configuration(
    context, monkeypatch, variable, old_value, new_value
):
    monkeypatch.setattr(shell, "which", lambda name: "/bin/" + name)
    if variable == "VAULT_EMBED_MODEL":
        context.values["model"] = new_value
    else:
        monkeypatch.setenv(variable, new_value)
    output = (
        "Scope: User (configuration)\nCommand: /bin/uv\nArgs: --directory "
        + context.values["repo"]
        + " run --no-dev vault-search-mcp\nEnvironment:\n  VAULT_ROOT="
        + context.values["vault"]
        + "\n  "
        + variable
        + "="
        + old_value
        + "\n"
    )
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, output, "")
    )
    assert not register.is_done(context)


def test_registration_detects_moved_repository(context, monkeypatch):
    monkeypatch.setattr(shell, "which", lambda name: "/bin/" + name)
    output = (
        "Scope: User (configuration)\nCommand: /bin/uv\n"
        "Args: --directory /alter-pfad run --no-dev vault-search-mcp\n"
        "Environment:\n  VAULT_ROOT=" + context.values["vault"] + "\n"
    )
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, output, "")
    )
    assert not register.is_done(context)
