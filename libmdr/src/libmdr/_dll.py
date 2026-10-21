"""ctypes loader for mdr-shared."""

from __future__ import annotations

import os
import sys
from ctypes import CDLL, RTLD_GLOBAL
from pathlib import Path

_LIB: CDLL | None = None

_ENV_OVERRIDE = "MDR_DLL"

_CANDIDATE_NAMES = (
    "mdr-shared.dll",
    "mdr.dll",
    "libmdr-shared.so",
    "libmdr-shared.dylib",
    "mdr-shared.so",
    "mdr-shared.dylib",
)


def _package_native_dir() -> Path:
    return Path(__file__).resolve().parent / "_native"


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        paths.append(Path(override))

    native = _package_native_dir()
    for name in _CANDIDATE_NAMES:
        paths.append(native / name)

    # Editable / in-tree builds may leave artifacts in the shared CMake tree.
    repo_build = Path(__file__).resolve().parents[4] / "build" / "python"
    if repo_build.is_dir():
        for name in _CANDIDATE_NAMES:
            paths.extend(repo_build.rglob(name))

    return paths


def _load_path(path: Path) -> CDLL:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    if sys.platform == "win32":
        os.add_dll_directory(str(path.parent))
        return CDLL(str(path))

    mode = RTLD_GLOBAL if hasattr(os, "RTLD_GLOBAL") else 0
    return CDLL(str(path), mode=mode)


def load() -> CDLL:
    global _LIB
    if _LIB is not None:
        return _LIB

    errors: list[str] = []
    seen: set[Path] = set()
    for candidate in _candidate_paths():
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            errors.append(f"{candidate}: {exc}")
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            _LIB = _load_path(resolved)
            return _LIB
        except OSError as exc:
            errors.append(f"{resolved}: {exc}")

    hint = (
        f"Set {_ENV_OVERRIDE} to the full path of mdr-shared "
        f"(or mdr.dll), or `pip install -e libmdr` to build it."
    )
    raise FileNotFoundError(
        "Unable to load mdr-shared.\n" + "\n".join(errors) + ("\n" + hint if errors else hint)
    )


def lib() -> CDLL:
    return load()
