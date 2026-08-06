"""ctypes loader for mdr-bt-shared (libmdr-bt)."""

from __future__ import annotations

import os
import sys
from ctypes import CDLL
from pathlib import Path

import libmdr._dll as libmdr_dll

_LIB: CDLL | None = None

_ENV_OVERRIDE = "MDR_BT_DLL"

_CANDIDATE_NAMES = (
    "mdr-bt-shared.dll",
    "libmdr-bt-shared.so",
    "libmdr-bt-shared.dylib",
    "mdr-bt-shared.so",
    "mdr-bt-shared.dylib",
)

_CORE_NAMES = (
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

    repo_build = Path(__file__).resolve().parents[4] / "build" / "python"
    if repo_build.is_dir():
        for name in _CANDIDATE_NAMES:
            paths.extend(repo_build.rglob(name))

    return paths


def _ensure_core_loaded(platform_dir: Path) -> None:
    if libmdr_dll._LIB is not None:  # noqa: SLF001
        return

    for name in _CORE_NAMES:
        sibling = platform_dir / name
        if sibling.is_file():
            libmdr_dll._LIB = libmdr_dll._load_path(sibling)  # noqa: SLF001
            return

    libmdr_dll.load()


def _load_path(path: Path) -> CDLL:
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)

    _ensure_core_loaded(path.parent)

    if sys.platform == "win32":
        os.add_dll_directory(str(path.parent))
        core_dir = libmdr_dll._package_native_dir()  # noqa: SLF001
        if core_dir.is_dir():
            os.add_dll_directory(str(core_dir))
        return CDLL(str(path))

    mode = os.RTLD_GLOBAL if hasattr(os, "RTLD_GLOBAL") else 0
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
        f"Set {_ENV_OVERRIDE} to the full path of mdr-bt-shared.dll, "
        f"or `pip install -e libmdr-bt` to build it."
    )
    raise FileNotFoundError(
        "Unable to load mdr-bt-shared.\n"
        + "\n".join(errors)
        + ("\n" + hint if errors else hint)
    )


def lib() -> CDLL:
    return load()
