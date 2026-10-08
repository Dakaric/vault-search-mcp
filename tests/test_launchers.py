import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_bash_launcher_from_other_directory(tmp_path):
    bash = shutil.which("bash")
    if not bash or sys.platform == "win32":
        pytest.skip("Bash wird auf Unix geprüft")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    executable = binaries / "uv"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import os, sys, json\n"
        'print(json.dumps({"args": sys.argv[1:], "path": os.environ["PYTHONPATH"]}))\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    environment = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"])
    result = subprocess.run(
        [bash, str(ROOT / "install.sh"), "--vault", str(tmp_path / "Mein Vault Ä"), "--yes"],
        cwd=tmp_path,
        env=environment,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["path"] == os.pathsep.join([str(ROOT), str(ROOT / "src")])
    assert data["args"] == [
        "run",
        "--no-project",
        "--directory",
        str(ROOT),
        "--python",
        "3.12",
        "python",
        "-m",
        "installer",
        "--vault",
        str(tmp_path / "Mein Vault Ä"),
        "--yes",
    ]


def powershell_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell_uv_fake(tmp_path, receiver, exit_code):
    if receiver == "function":
        return (
            "function global:uv { ConvertTo-Json -InputObject $args -Compress; "
            "Write-Output $env:PYTHONPATH; "
            f"$global:LASTEXITCODE = {exit_code} }}\n"
        )
    recorder = tmp_path / "Argumente prüfen.py"
    recorder.write_text(
        "import json, os, sys\n"
        "sys.stdout.reconfigure(encoding='utf-8')\n"
        "print(json.dumps(sys.argv[1:]))\n"
        "print(os.environ['PYTHONPATH'])\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return (
        f"function global:uv {{ & {powershell_quote(sys.executable)} "
        f"{powershell_quote(recorder)} @args; "
        "$global:LASTEXITCODE = $LASTEXITCODE }\n"
    )


@pytest.mark.parametrize("receiver", ["function", "native"])
@pytest.mark.parametrize("exit_code", [0, 23])
def test_powershell_launcher_from_other_directory(tmp_path, receiver, exit_code):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell ist lokal nicht installiert")
    repo = tmp_path / "Quellcode fürs Prüfen"
    repo.mkdir()
    shutil.copy2(ROOT / "install.ps1", repo / "install.ps1")
    wrapper = tmp_path / "run.ps1"
    forwarded = ["--yes", "--vault", "C:\\Mein Vault\\Anhänge\\", "--model", "3.12"]
    # Die BOM hält den UTF-8-Wrapper auch mit Windows PowerShell 5.1 lesbar.
    wrapper.write_text(
        "\ufeff[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
        + powershell_uv_fake(tmp_path, receiver, exit_code)
        + "& "
        + " ".join(powershell_quote(arg) for arg in [repo / "install.ps1", *forwarded])
        + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == exit_code, result.stderr
    lines = result.stdout.strip().splitlines()
    assert json.loads(lines[0]) == [
        "run",
        "--no-project",
        "--directory",
        str(repo),
        "--python",
        "3.12",
        "python",
        "-m",
        "installer",
        *forwarded,
    ]
    assert lines[1] == os.pathsep.join([str(repo), str(repo / "src")])
