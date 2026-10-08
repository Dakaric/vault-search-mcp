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


def test_powershell_launcher_from_other_directory(tmp_path):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell ist lokal nicht installiert")
    wrapper = tmp_path / "run.ps1"
    launcher = str(ROOT / "install.ps1").replace("'", "''")
    wrapper.write_text(
        "function global:uv { $args | ConvertTo-Json -Compress; "
        "Write-Output $env:PYTHONPATH; $global:LASTEXITCODE = 0 }\n"
        + "& '"
        + launcher
        + "' --yes --vault 'C:\\Mein Vault\\Anhänge'\n",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert json.loads(lines[0]) == [
        "run",
        "--no-project",
        "--directory",
        str(ROOT),
        "--python",
        "3.12",
        "python",
        "-m",
        "installer",
        "--yes",
        "--vault",
        "C:\\Mein Vault\\Anhänge",
    ]
    assert lines[1] == os.pathsep.join([str(ROOT), str(ROOT / "src")])
