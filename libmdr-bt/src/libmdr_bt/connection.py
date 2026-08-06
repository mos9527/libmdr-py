"""Platform connection factories wrapping mdr-bt-shared (libmdr-bt)."""

from __future__ import annotations

import sys
from ctypes import c_void_p
from typing import Literal

from libmdr.connection import Connection

from . import _dll

Backend = Literal["auto", "classic", "ble"]


def _bind_factory(create_name: str, get_name: str, destroy_name: str):
    lib = _dll.lib()
    create = getattr(lib, create_name)
    getter = getattr(lib, get_name)
    destroy = getattr(lib, destroy_name)

    create.restype = c_void_p
    create.argtypes = []
    getter.restype = c_void_p
    getter.argtypes = [c_void_p]
    destroy.restype = None
    destroy.argtypes = [c_void_p]
    return create, getter, destroy


class PlatformConnection:
    """Owns a platform-specific connection object and exposes the MDRConnection vtable."""

    def __init__(self, backend: Backend = "auto") -> None:
        self._backend = "classic" if backend == "auto" else backend
        self._owner: c_void_p | None = None
        self._connection: Connection | None = None
        self._destroy = None
        self._create()

    def _factories(self):
        platform = sys.platform
        if platform == "win32":
            if self._backend == "ble":
                return _bind_factory(
                    "mdrConnectionWindowsBLECreate",
                    "mdrConnectionWindowsBLEGet",
                    "mdrConnectionWindowsBLEDestroy",
                )
            return _bind_factory(
                "mdrConnectionWindowsCreate",
                "mdrConnectionWindowsGet",
                "mdrConnectionWindowsDestroy",
            )
        if platform == "darwin":
            if self._backend == "ble":
                raise RuntimeError("BLE backend is not available on macOS in mdr-bt-shared")
            return _bind_factory(
                "mdrConnectionMacOSCreate",
                "mdrConnectionMacOSGet",
                "mdrConnectionMacOSDestroy",
            )
        if platform.startswith("linux"):
            if self._backend == "ble":
                raise RuntimeError("BLE backend is not available on Linux in mdr-bt-shared")
            return _bind_factory(
                "mdrConnectionLinuxCreate",
                "mdrConnectionLinuxGet",
                "mdrConnectionLinuxDestroy",
            )
        raise RuntimeError(f"Unsupported platform for libmdr-bt bindings: {platform}")

    def _create(self) -> None:
        create, getter, destroy = self._factories()
        owner = create()
        if not owner:
            raise RuntimeError(f"Failed to create platform connection ({self._backend})")
        connection = getter(owner)
        if not connection:
            destroy(owner)
            raise RuntimeError("Platform connection Get() returned null")

        self._destroy = destroy
        self._owner = c_void_p(owner)
        self._connection = Connection(connection)

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def connection(self) -> Connection:
        if self._connection is None:
            raise RuntimeError("Platform connection is closed")
        return self._connection

    def close(self) -> None:
        if self._owner is not None and self._destroy is not None:
            self._destroy(self._owner)
            self._owner = None
            self._connection = None

    def __enter__(self) -> PlatformConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def devices(self):
        return self.connection.devices()

    def connect(self, mac_address: str, service_uuid: str) -> int:
        return self.connection.connect(mac_address, service_uuid)

    def disconnect(self) -> None:
        self.connection.disconnect()

    def poll(self, timeout_ms: int = 0) -> int:
        return self.connection.poll(timeout_ms)

    def last_error(self) -> str:
        return self.connection.last_error()


def create_connection(*, ble: bool = False, backend: Backend | None = None) -> PlatformConnection:
    """Create the host platform connection.

    Prefer `ble=True` / `backend="ble"` on Windows when talking over GATT.
    """
    if backend is None:
        backend = "ble" if ble else "classic"
    return PlatformConnection(backend=backend)
