import json
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

Json = dict | list


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.sicherung-{stamp}")
    number = 1
    while target.exists():
        target = path.with_name(f"{path.name}.sicherung-{stamp}-{number}")
        number += 1
    if path.is_dir():
        shutil.copytree(path, target, symlinks=True)
    else:
        shutil.copy2(path, target)
    return target


def merge_json(base: Json, extra: Json) -> Json:
    result = deepcopy(base)
    if isinstance(result, dict) and isinstance(extra, dict):
        for key, value in extra.items():
            if key not in result:
                result[key] = deepcopy(value)
            elif isinstance(result[key], (dict, list)):
                result[key] = merge_json(result[key], value)
    elif isinstance(result, list) and isinstance(extra, list):
        for value in extra:
            if value not in result:
                result.append(deepcopy(value))
    return result


def read_json(path: Path, empty: Json) -> Json:
    if not path.exists():
        return deepcopy(empty)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, (dict, list)):
        raise ValueError(f"JSON muss ein Objekt oder eine Liste enthalten: {path}")
    return data


def write_json(path: Path, data: Json) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_rmtree(path: Path, allowed_root: Path) -> None:
    resolved, root = path.resolve(), allowed_root.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f"Löschen außerhalb des Cache-Unterordners verweigert: {path}")
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
