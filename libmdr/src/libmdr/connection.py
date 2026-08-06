"""High-level wrapper around MDRConnection helpers."""

from __future__ import annotations

from ctypes import POINTER, byref, c_int, cast, c_void_p
from dataclasses import dataclass

from . import _api, _dll, result


@dataclass(frozen=True)
class DeviceInfo:
    name: str
    address: str


class Connection:
    """Thin wrapper over an `MDRConnection*` owned elsewhere (usually libmdr_bt)."""

    def __init__(self, ptr: object) -> None:
        if not ptr:
            raise ValueError("MDRConnection pointer is null")
        self._ptr = cast(ptr, POINTER(_api.MDRConnection))

    @property
    def pointer(self):
        return self._ptr

    def as_void_p(self) -> c_void_p:
        return cast(self._ptr, c_void_p)

    def connect(self, mac_address: str, service_uuid: str) -> int:
        return result.check(
            _dll.lib().mdrConnectionConnect(
                self._ptr,
                mac_address.encode("utf-8"),
                service_uuid.encode("utf-8"),
            ),
            allow_inprogress=True,
        )

    def disconnect(self) -> None:
        _dll.lib().mdrConnectionDisconnect(self._ptr)

    def poll(self, timeout_ms: int = 0) -> int:
        return int(_dll.lib().mdrConnectionPoll(self._ptr, int(timeout_ms)))

    def last_error(self) -> str:
        text = _dll.lib().mdrConnectionGetLastError(self._ptr)
        if not text:
            return ""
        return text.decode("utf-8", errors="replace")

    def devices(self) -> list[DeviceInfo]:
        lib = _dll.lib()
        devices = POINTER(_api.MDRDeviceInfo)()
        count = c_int(0)
        result.check(lib.mdrConnectionGetDevicesList(self._ptr, byref(devices), byref(count)))
        try:
            out: list[DeviceInfo] = []
            for index in range(count.value):
                item = devices[index]
                out.append(
                    DeviceInfo(
                        name=item.szDeviceName.decode("utf-8", errors="replace").rstrip("\x00"),
                        address=item.szDeviceMacAddress.decode("utf-8", errors="replace").rstrip(
                            "\x00"
                        ),
                    )
                )
            return out
        finally:
            result.check(lib.mdrConnectionFreeDevicesList(self._ptr, byref(devices)))
