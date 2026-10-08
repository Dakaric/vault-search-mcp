import io
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

from installer import cli, fsutil, platform, shell, ui
from installer.model import Context, Result, Support
from installer.run import run_components


@pytest.fixture
def context(tmp_path):
    return Context("linux", tmp_path, False, True, {})


def component(key="demo", **overrides):
    values = dict(
        KEY=key,
        TITLE=key,
        DESCRIPTION="Ein Baustein",
        DEFAULT=True,
        supported=lambda p: Support("ja"),
        is_done=lambda c: False,
        plan=lambda c: ["Plan anzeigen"],
        apply=lambda c: Result(key, "erledigt"),
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_merge_keeps_user_entries():
    original = {"mcpServers": {"mine": {"args": ["eigene"]}}, "theme": "dunkel"}
    extra = {"mcpServers": {"new": {}}, "theme": "hell"}
    merged = fsutil.merge_json(original, extra)
    assert merged == {"mcpServers": {"mine": {"args": ["eigene"]}, "new": {}}, "theme": "dunkel"}
    assert "new" not in original["mcpServers"]


def test_merge_lists_without_duplicates():
    assert fsutil.merge_json({"plugins": ["a", "b"]}, {"plugins": ["b", "c"]}) == {
        "plugins": ["a", "b", "c"]
    }


def test_merge_top_level_list():
    assert fsutil.merge_json(["a", "b"], ["b", "c"]) == ["a", "b", "c"]


def test_merge_list_of_dicts():
    assert fsutil.merge_json([{"id": 1}], [{"id": 1}, {"id": 2}]) == [{"id": 1}, {"id": 2}]


def test_backup_names_copy_with_timestamp(tmp_path):
    path = tmp_path / "settings.json"
    assert fsutil.backup(path) is None
    path.write_text("Änderung", encoding="utf-8")
    saved = fsutil.backup(path)
    assert re.match(r"settings.json.sicherung-\d{8}-\d{6}", saved.name)
    assert saved.read_text(encoding="utf-8") == "Änderung"
    path.write_text("Zweiter Stand", encoding="utf-8")
    second = fsutil.backup(path)
    assert second != saved
    assert saved.read_text(encoding="utf-8") == "Änderung"


def test_backup_directory(tmp_path):
    folder = tmp_path / "config"
    folder.mkdir()
    (folder / "a.json").write_text("{}", encoding="utf-8")
    saved = fsutil.backup(folder)
    assert (saved / "a.json").read_text(encoding="utf-8") == "{}"


def test_safe_rmtree_refuses_outside_root(tmp_path):
    with pytest.raises(ValueError):
        fsutil.safe_rmtree(tmp_path / "other", tmp_path / "cache")


def test_safe_rmtree_refuses_root_itself(tmp_path):
    with pytest.raises(ValueError):
        fsutil.safe_rmtree(tmp_path, tmp_path)


def test_safe_rmtree_removes_only_cache_child(tmp_path):
    child = tmp_path / "cache" / "download"
    child.mkdir(parents=True)
    (child / "file").write_text("Inhalt", encoding="utf-8")
    fsutil.safe_rmtree(child, tmp_path / "cache")
    assert not child.exists()
    assert (tmp_path / "cache").exists()


def test_safe_rmtree_refuses_symlink_escape(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (cache / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks auf diesem System nicht freigegeben")
    with pytest.raises(ValueError):
        fsutil.safe_rmtree(cache / "link", cache)
    assert outside.exists()


@pytest.mark.parametrize(
    ("system", "name"), [("darwin", "macos"), ("linux", "linux"), ("win32", "windows")]
)
def test_cache_dir_per_platform(system, name, monkeypatch, context):
    monkeypatch.setattr(sys, "platform", system)
    monkeypatch.setenv("LOCALAPPDATA", str(context.home / "Local Data"))
    context.platform = platform.detect()
    assert context.platform == name
    expected = context.home / ("Local Data/demo/cache" if name == "windows" else ".cache/demo")
    assert platform.cache_dir("demo", context) == expected


def test_no_tty_without_yes_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    assert cli.main([]) == 2
    assert "--yes" in capsys.readouterr().out


def test_failing_component_does_not_stop_others(context):
    def fail(ctx):
        raise OSError("Download fehlgeschlagen")

    results = run_components([component("bad", apply=fail), component("good")], context, None)
    assert [r.status for r in results] == ["fehler", "erledigt"]
    assert "Download" in results[0].detail


def test_probe_failure_does_not_stop_others(context):
    def fail(ctx):
        raise OSError("Prüfung fehlgeschlagen")

    results = run_components([component("bad", is_done=fail), component("good")], context, None)
    assert [r.status for r in results] == ["fehler", "erledigt"]


def test_dry_run_applies_nothing(context):
    context.dry_run = True

    def forbidden(ctx):
        pytest.fail("Dry-Run darf weder ausführen noch Dienste abfragen")

    results = run_components([component(is_done=forbidden, apply=forbidden)], context, None)
    assert results[0].status == "übersprungen"
    assert "Plan anzeigen" in results[0].detail


def test_selection_support_and_idempotence(context):
    components = [
        component("unused"),
        component("done", is_done=lambda c: True),
        component("no", supported=lambda p: Support("nein", "Kein Programm")),
        component("off", DEFAULT=False),
    ]
    results = run_components(components, context, {"done", "no", "off"})
    assert [(r.key, r.status) for r in results] == [
        ("done", "übersprungen"),
        ("no", "nicht unterstützt"),
        ("off", "übersprungen"),
    ]
    assert "schon eingerichtet" in results[0].detail


def test_cli_unknown_only_exits_2():
    assert cli.main(["--yes", "--dry-run", "--only", "vertippt"]) == 2


def test_cli_error_exit_code(monkeypatch):
    monkeypatch.setattr(cli, "run_components", lambda *args: [Result("x", "fehler", "Fehler")])
    assert cli.main(["--yes", "--only", "ollama"]) == 1


def test_json_roundtrip_utf8(tmp_path):
    target = tmp_path / "Mein Vault" / "einstellungen.json"
    assert fsutil.read_json(target, []) == []
    fsutil.write_json(target, {"Ordner": "07 Anhänge"})
    assert "Anhänge" in target.read_text(encoding="utf-8")
    assert target.read_bytes().endswith(b"\n")
    assert fsutil.read_json(target, {}) == {"Ordner": "07 Anhänge"}


def test_shell_paths_with_spaces_and_umlauts(context, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw)))
    shell.run(["tool", "Mein Vault/07 Anhänge"], context)
    assert calls[0][0] == ["tool", "Mein Vault/07 Anhänge"]
    assert not calls[0][1].get("shell", False)
    context.dry_run = True
    shell.run(["other"], context)
    assert len(calls) == 1


def test_ui_yes_uses_defaults_without_input(context, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("Kein Dialog bei --yes"))
    assert ui.ask_yes_no("Ausführen?", False, context) is False
    assert ui.ask_text("Pfad?", "Vorgabe", context) == "Vorgabe"
