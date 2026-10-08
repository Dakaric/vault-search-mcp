from pathlib import PurePath


def rel_posix(path: PurePath, root: PurePath) -> str:
    return path.relative_to(root).as_posix()
