"""Build script for libmdr-bt (also the setuptools entry point).

The CMake build helpers that previously lived in a separate ``cmake_build.py``
are inlined here. Like that module, this is build-time code and is NOT packaged
into the wheel; it runs only during ``build_py`` / ``editable_wheel`` to compile
and stage the native shared library into the package's ``_native`` directory.

C++ source resolution order:
  1. ``MDR_SOURCE_DIR`` env var            (explicit override)
  2. ``<repo>/cpp``                        (git submodule, preferred)
  3. ``<repo>/build/cpp-src``              (fresh shallow clone on every build)

The third option lets ``pip install .`` / ``python -m build`` work from a
plain source checkout or sdist without the caller having to run
``git submodule update --init`` first.
"""

from __future__ import annotations

import configparser
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.editable_wheel import editable_wheel as _editable_wheel

# Python repo root (this file lives in <repo>/<pkg>/setup.py).
_PY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUILD_DIR = _PY_ROOT / "build" / "python"
# Fresh C++ source clone location (separate from the CMake build dir so the
# build dir can be wiped between builds without discarding the clone).
_CLONE_DIR = _PY_ROOT / "build" / "cpp-src"
# Preferred on-disk location of the C++ sources.
_SUBMODULE_DIR = _PY_ROOT / "cpp"
# Upstream coordinates, used only when cloning on demand. These mirror
# .gitmodules and are overridden by it when the file is present.
_SOURCE_URL = "https://github.com/mos9527/SonyHeadphonesClient.git"
_SOURCE_BRANCH = "v1-compat"

# CMake target -> on-disk base name (OUTPUT_NAME set in the C++ CMakeLists).
_TARGET_BASENAMES = {
    "mdr_shared": "mdr-shared",
    "mdr-bt_shared": "mdr-bt-shared",
}
_SUFFIXES = (".dll", ".so", ".dylib")


def _cmake() -> str:
    env = os.environ.get("CMAKE")
    if env:
        return env
    found = shutil.which("cmake")
    if found:
        return found
    raise RuntimeError("cmake not found on PATH; install CMake or set CMAKE.")


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd)


def _read_gitmodules() -> tuple[str, str] | None:
    """Return (url, branch) for the 'cpp' submodule from .gitmodules, if present."""
    gm = _PY_ROOT / ".gitmodules"
    if not gm.is_file():
        return None
    cp = configparser.ConfigParser()
    cp.read(gm, encoding="utf-8")
    for section in cp.sections():
        if cp.has_option(section, "path") and cp.get(section, "path") == "cpp":
            url = cp.get(section, "url", fallback=_SOURCE_URL)
            branch = cp.get(section, "branch", fallback=_SOURCE_BRANCH)
            return url, branch
    return None


def _rmtree(path: Path) -> None:
    """Remove a directory tree, tolerating read-only files (git marks .git
    objects read-only on Windows) and transient file locks."""
    if not path.exists():
        return

    def _clear_ro(func, p, exc):  # noqa: ANN001
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            raise

    last_err: OSError | None = None
    for _ in range(3):
        try:
            if sys.version_info >= (3, 12):
                shutil.rmtree(path, onexc=_clear_ro)
            else:
                shutil.rmtree(path, onerror=_clear_ro)
            return
        except OSError as exc:
            last_err = exc
            time.sleep(0.5)
    if last_err:
        raise last_err


def _clone_source(dest: Path) -> None:
    url, branch = _read_gitmodules() or (_SOURCE_URL, _SOURCE_BRANCH)
    _rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--depth", "1", "--branch", branch, url, str(dest)])


def _ensure_source() -> Path:
    """Resolve the C++ source directory, cloning it into the build dir if needed."""
    override = os.environ.get("MDR_SOURCE_DIR")
    if override:
        return Path(override)
    if _SUBMODULE_DIR.is_dir() and any(_SUBMODULE_DIR.iterdir()):
        return _SUBMODULE_DIR
    clone_dir = _CLONE_DIR
    print(f"cpp source not found at {_SUBMODULE_DIR}; cloning latest into {clone_dir}", flush=True)
    _clone_source(clone_dir)
    return clone_dir


def _configure(build_dir: Path | None = None, *, extra_args: list[str] | None = None) -> Path:
    build_dir = Path(build_dir or os.environ.get("MDR_PYTHON_BUILD_DIR", DEFAULT_BUILD_DIR))
    # Always start from a clean build dir so a stale CMake cache or an
    # interrupted dependency fetch (e.g. fmt via FetchContent) cannot poison
    # the next configure. The C++ source is re-cloned separately each time.
    _rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        _cmake(), "-S", str(_ensure_source()), "-B", str(build_dir),
        "-DBUILD_TESTING=OFF",
        "-DMDR_BUILD_CLIENT=OFF",
        "-DMDR_ENABLE_CODEGEN=OFF",
        "-DMDR_CLIENT_DEBUGGER=OFF",
        "-DMDR_ENABLE_LOG=OFF",
    ]
    if extra_args:
        cmd.extend(extra_args)
    gen = os.environ.get("MDR_CMAKE_GENERATOR")
    if gen:
        cmd[1:1] = ["-G", gen]
    _run(cmd)
    return build_dir


def _build(targets: list[str], build_dir: Path | None = None, *, config: str | None = None, extra_args: list[str] | None = None) -> Path:
    build_dir = _configure(build_dir, extra_args=extra_args)
    config = config or os.environ.get("MDR_CMAKE_CONFIG", "Release")
    cmd = [_cmake(), "--build", str(build_dir), "--config", config, "--parallel"]
    for target in targets:
        cmd.extend(["--target", target])
    _run(cmd)
    return build_dir


def _output_dir_args(destination: Path) -> list[str]:
    # Redirect shared-lib output into `destination`; per-config generators
    # still nest a <CONFIG> subdir, which stage_libraries() flattens.
    d = str(destination)
    return [
        f"-DCMAKE_RUNTIME_OUTPUT_DIRECTORY={d}",
        f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={d}",
    ]


def _find_built(destination: Path, target: str) -> Path:
    base = _TARGET_BASENAMES[target]
    names = {f"{base}{suf}" for suf in _SUFFIXES}
    names |= {f"lib{base}{suf}" for suf in (".so", ".dylib")}
    for path in destination.rglob("*"):
        if path.is_file() and path.name in names:
            return path.resolve()
    raise FileNotFoundError(
        f"Built library for {target} not found under {destination}. "
        f"Looked for: {', '.join(sorted(names))}"
    )


def stage_libraries(targets: list[str], destination: Path) -> list[Path]:
    """Build the shared targets and emit them (flattened) into `destination`."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    _build(targets, extra_args=_output_dir_args(destination))
    staged: list[Path] = []
    for target in targets:
        found = _find_built(destination, target)
        final = destination / found.name  # flatten any <CONFIG> subdir
        if found.resolve() != final.resolve():
            shutil.copy2(found, final)
        staged.append(final)
    return staged


def stage_library(target: str, destination: Path) -> Path:
    """Build one shared target and emit it (flattened) into `destination`."""
    return stage_libraries([target], destination)[0]


def _stage_native() -> None:
    destination = Path(__file__).resolve().parent / "src" / "libmdr_bt" / "_native"
    # libmdr-bt links the core statically (PRIVATE mdr), so mdr-bt-shared is
    # self-contained; the core mdr-shared is provided by the libmdr dependency.
    stage_libraries(["mdr-bt_shared"], destination)


class build_py(_build_py):
    def run(self) -> None:
        _stage_native()
        super().run()


class editable_wheel(_editable_wheel):
    def run(self) -> None:
        _stage_native()
        super().run()


setup(
    cmdclass={
        "build_py": build_py,
        "editable_wheel": editable_wheel,
    }
)
