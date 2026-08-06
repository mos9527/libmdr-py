"""Result codes and helpers for the mdr C ABI."""

from __future__ import annotations

from . import _dll

ABI_VERSION = 1

OK = 0
INPROGRESS = 1
ERROR_GENERAL = 2
ERROR_NOT_FOUND = 3
ERROR_TIMEOUT = 4
ERROR_NET = 5
ERROR_NO_CONNECTION = 6
ERROR_BAD_ADDRESS = 7
ERROR_NOT_SUPPORTED = 8
ERROR_BUFFER_TOO_SMALL = 9
ERROR_MALFORMED_PAYLOAD = 10
ERROR_INVALID_ARGUMENT = 11
ERROR_ABI_MISMATCH = 12

SERVICE_UUID_XM5 = "956C7B26-D49A-4BA8-B03F-B17D393CB6E2"
SERVICE_UUID_LEGACY = "96CC203E-5068-46AD-B32D-E316F5E069BA"
BLE_SERVICE_UUID_TANDEM_OVER_BLE_HPC = "5B833E20-6BC7-4802-8E9A-723CECA4BD8F"

INIT_BT_BLE = 1 << 0


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
