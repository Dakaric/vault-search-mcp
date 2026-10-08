import os
import re
import subprocess
from pathlib import PureWindowsPath

from installer import shell, ui
from installer.components import model, vault
from installer.model import Context, Platform, Result, Support
from vault_search.config import DEFAULT_EMBED_MODEL, DEFAULT_OLLAMA_URL, EMBED_DIMENSIONS

KEY = "registrieren"
TITLE = "In Claude Code registrieren"
DESCRIPTION = "MCP-Server vault-search für das Benutzerkonto eintragen."
DEFAULT = True


def supported(platform: Platform) -> Support:
    return Support("ja")


def _registration(ctx: Context):
    claude = shell.which("claude")
    if not claude:
        return None
    result = shell.capture([claude, "mcp", "get", "vault-search"])
    return result if result.returncode == 0 else None


def _environment(ctx: Context) -> dict[str, str]:
    values = {
        "VAULT_ROOT": ctx.values.get("vault", ""),
        "VAULT_EMBED_MODEL": model.model_name(ctx),
    }
    for name in ("OLLAMA_URL", "VAULT_EMBED_DIM", "VAULT_INDEX_DIR", "VAULT_IGNORE_DIRS"):
        if name in os.environ:
            values[name] = os.environ[name]
    return values


def is_done(ctx: Context) -> bool:
    registration = _registration(ctx)
    if registration is None:
        return False
    fields = _fields(registration.stdout, ":")
    if not _owned_registration(fields):
        return False
    expected_args = f"--directory {ctx.values['repo']} run --no-dev vault-search-mcp"
    if fields.get("Command") != shell.which("uv") or fields.get("Args") != expected_args:
        return False
    saved = _saved_environment(registration.stdout)
    defaults = {
        "VAULT_EMBED_MODEL": DEFAULT_EMBED_MODEL,
        "OLLAMA_URL": DEFAULT_OLLAMA_URL,
        "VAULT_EMBED_DIM": str(EMBED_DIMENSIONS),
        "VAULT_IGNORE_DIRS": "",
    }
    expected = _environment(ctx)
    for key in set(expected) | (set(saved) & set(defaults)):
        if saved.get(key, defaults.get(key)) != expected.get(key, defaults.get(key)):
            return False
    return saved.get("VAULT_INDEX_DIR") == expected.get("VAULT_INDEX_DIR")


def command(ctx: Context) -> list[str]:
    args = [shell.which("claude") or "claude", "mcp", "add", "vault-search", "--scope", "user"]
    for name, value in _environment(ctx).items():
        args.extend(["-e", f"{name}={value}"])
    args.extend(
        [
            "--",
            shell.which("uv") or "uv",
            "--directory",
            ctx.values["repo"],
            "run",
            "--no-dev",
            "vault-search-mcp",
        ]
    )
    return args


def plan(ctx: Context) -> list[str]:
    return [shell.format_command(command(ctx), ctx.platform)]


def _fields(output: str, separator: str) -> dict[str, str]:
    fields = {}
    for line in output.splitlines():
        key, found, value = line.strip().partition(separator)
        if found:
            fields[key] = value.strip()
    return fields


def _owned_registration(fields: dict[str, str]) -> bool:
    return (
        fields.get("Scope", "").split(" (", 1)[0].lower() in {"user", "user config"}
        and PureWindowsPath(fields.get("Command", "")).name.lower() in {"uv", "uv.exe"}
        and _registered_args(fields.get("Args", "")) is not None
    )


def _registered_args(value: str) -> list[str] | None:
    match = re.fullmatch(r"(?:--directory (.+) )?run( --no-dev)? vault-search-mcp", value)
    if match is None:
        return None
    directory, no_dev = match.groups()
    args = ["--directory", directory] if directory else []
    return args + ["run"] + (["--no-dev"] if no_dev else []) + ["vault-search-mcp"]


def _saved_environment(output: str) -> dict[str, str]:
    values = {}
    in_environment = False
    for line in output.splitlines():
        if line.strip() == "Environment:":
            in_environment = True
            continue
        if in_environment and line and not line[0].isspace():
            break
        if in_environment:
            key, separator, value = line.strip().partition("=")
            if separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                values[key] = value
    return values


def _recovery_command(output: str, ctx: Context) -> str:
    fields = _fields(output, ":")
    args = [shell.which("claude") or "claude", "mcp", "add", "vault-search", "--scope", "user"]
    for name, value in _saved_environment(output).items():
        args.extend(["-e", f"{name}={value}"])
    args.extend(["--", fields["Command"], *_registered_args(fields["Args"])])
    return shell.format_command(args, ctx.platform)


def _replace_registration(output: str, ctx: Context, instructions: str) -> Result:
    if not _owned_registration(_fields(output, ":")):
        return Result(
            KEY,
            "handarbeit",
            "Vorhandener Eintrag gehört nicht zum Installer. "
            "Eintrag von Hand prüfen. Registrierungsbefehl: " + instructions,
        )
    if not ui.ask_yes_no("Vorhandenen Benutzer-Eintrag vault-search ersetzen?", False, ctx):
        return Result(
            KEY, "handarbeit", "Eintrag beibehalten. Registrierungsbefehl: " + instructions
        )
    recovery = _recovery_command(output, ctx)
    shell.run([shell.which("claude"), "mcp", "remove", "vault-search", "-s", "user"], ctx)
    try:
        shell.run(command(ctx), ctx)
    except (OSError, subprocess.SubprocessError) as error:
        return Result(
            KEY,
            "fehler",
            f"Registrierung fehlgeschlagen: {error}. Wiederherstellen mit: " + recovery,
        )
    return Result(KEY, "erledigt", "vault-search ist in Claude Code registriert.")


def apply(ctx: Context) -> Result:
    instructions = shell.format_command(command(ctx), ctx.platform)
    if not shell.which("claude") or not shell.which("uv"):
        return Result(
            KEY,
            "handarbeit",
            "Claude Code und uv müssen im PATH sein. Danach ausführen: " + instructions,
        )
    vault.validate(ctx.values.get("vault", ""))
    registration = _registration(ctx)
    if registration is not None:
        return _replace_registration(registration.stdout, ctx, instructions)
    shell.run(command(ctx), ctx)
    return Result(KEY, "erledigt", "vault-search ist in Claude Code registriert.")
