import shlex
import shutil
import subprocess

from installer.model import Context, Platform


def which(name: str) -> str | None:
    return shutil.which(name)


def format_command(cmd: list[str], platform: Platform) -> str:
    if platform == "windows":

        def quote(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        return "& " + " ".join(quote(value) for value in cmd)
    return shlex.join(cmd)


def run(
    cmd: list[str], ctx: Context, check: bool = True, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess | None:
    print("$ " + format_command(cmd, ctx.platform))
    if ctx.dry_run:
        return None
    return subprocess.run(cmd, check=check, env=env)


def capture(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
