import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = tuple(
    "".join(parts)
    for parts in (
        ("christ", "ian"),
        ("lan", "ger"),
        ("dan", "iel"),
        ("har", "ry"),
        ("chris", "_brain"),
        ("chris", "-brain"),
        ("koe", "mpf"),
        ("kö", "mpf"),
        ("ae", "nd"),
        ("æ", "nd"),
        ("/us", "ers/"),
        ("\\us", "ers\\"),
        ("jar", "vis"),
        ("pfä", "ffle"),
        ("joch", "en"),
    )
)
OWNER = "Daka" + "ric"
DASH = re.compile(r"\u2014|\s\u2013\s|\D\u2013|\u2013\D")


def repository_files():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    files = [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]
    assert files, "Wächter braucht Dateien zum Prüfen"
    return [p for p in files if p.is_file() and p.name != "uv.lock"]


def personal_terms(text, path):
    lowered = text.lower()
    hits = [term for term in FORBIDDEN if term in lowered]
    cleaned = re.sub(r"https://github\.com/" + OWNER + r"/[^\s)\]]+", "", text)
    if path.name == "LICENSE":
        cleaned = cleaned.replace(OWNER, "")
    if path.name == "pyproject.toml":
        cleaned = cleaned.replace('authors = [{ name = "' + OWNER + '" }]', "")
    if OWNER.lower() in cleaned.lower():
        hits.append(OWNER)
    return hits


def test_no_personal_terms():
    assert personal_terms("Ein " + FORBIDDEN[0].upper(), Path("example.md"))
    assert personal_terms(OWNER, Path("example.md"))
    assert not personal_terms(
        "https://github.com/" + OWNER + "/vault-search-mcp", Path("README.md")
    )
    failures = {
        str(p.relative_to(ROOT)): personal_terms(p.read_text(encoding="utf-8"), p)
        for p in repository_files()
    }
    assert not {p: hits for p, hits in failures.items() if hits}


def test_no_dash_as_aside():
    assert DASH.search("Text " + chr(0x2014) + " Einschub")
    assert DASH.search("Text " + chr(0x2013) + " Einschub")
    assert not DASH.search("2020" + chr(0x2013) + "2024")
    failures = [
        str(p.relative_to(ROOT))
        for p in repository_files()
        if p.suffix in {".md", ".py", ".json", ".ps1", ".sh", ".yml", ".toml"}
        and DASH.search(p.read_text(encoding="utf-8"))
    ]
    assert not failures


def test_windows_home_path_is_detected():
    assert personal_terms("C:" + "\\us" + "ers\\Example\\note.md", Path("example.md"))


@pytest.mark.parametrize("suffix", [".ps1", ".sh", ".yml", ".toml"])
def test_dash_guard_checks_script_and_config_files(tmp_path, monkeypatch, suffix):
    target = tmp_path / ("example" + suffix)
    target.write_text("Text " + chr(0x2014) + " Einschub", encoding="utf-8")
    monkeypatch.setattr(__name__ + ".ROOT", tmp_path)
    monkeypatch.setattr(__name__ + ".repository_files", lambda: [target])
    with pytest.raises(AssertionError):
        test_no_dash_as_aside()
