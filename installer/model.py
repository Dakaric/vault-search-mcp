from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Platform = Literal["macos", "linux", "windows"]


@dataclass(frozen=True)
class Support:
    state: Literal["ja", "nein", "ungetestet"]
    reason: str = ""


@dataclass(frozen=True)
class Result:
    key: str
    status: Literal["erledigt", "übersprungen", "nicht unterstützt", "handarbeit", "fehler"]
    detail: str = ""


@dataclass
class Context:
    platform: Platform
    home: Path
    dry_run: bool
    assume_yes: bool
    values: dict[str, str]
