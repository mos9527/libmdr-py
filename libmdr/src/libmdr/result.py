"""Result codes and helpers for the mdr C ABI."""

from __future__ import annotations

from . import _dll
from ._generated_result import *  # noqa: F403


class MDRError(RuntimeError):
    def __init__(self, code: int, message: str | None = None) -> None:
        self.code = int(code)
        super().__init__(message or result_string(self.code))


def result_string(code: int) -> str:
    from . import _api  # noqa: F401  # ensure prototypes are bound

    lib = _dll.lib()
    text = lib.mdrResultString(code)
    if not text:
        return f"MDR_RESULT_{code}"
    return text.decode("utf-8", errors="replace")


def check(code: int, *, allow_inprogress: bool = False) -> int:
    code = int(code)
    if code == OK or (allow_inprogress and code == INPROGRESS):
        return code
    raise MDRError(code)
