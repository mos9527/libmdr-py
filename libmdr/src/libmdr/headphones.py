"""High-level wrapper around MDRHeadphones."""

from __future__ import annotations

from ctypes import byref, c_uint32, c_void_p, create_string_buffer
from typing import TYPE_CHECKING

from . import _api, _dll, constants, result
from .connection import Connection

if TYPE_CHECKING:
    from collections.abc import Callable


class Headphones:
    def __init__(self, connection: Connection, *, abi_version: int = result.ABI_VERSION) -> None:
        handle = c_void_p()
        result.check(
            _dll.lib().mdrHeadphonesCreate(
                abi_version,
                connection.pointer,
                byref(handle),
            )
        )
        if not handle:
            raise result.MDRError(result.ERROR_GENERAL, "mdrHeadphonesCreate returned a null handle")
        self._handle = handle
        self._packet_callback = None

    def close(self) -> None:
        if self._handle:
            _dll.lib().mdrHeadphonesDestroy(self._handle)
            self._handle = None
            self._packet_callback = None

    def __enter__(self) -> Headphones:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    @property
    def handle(self):
        if not self._handle:
            raise result.MDRError(result.ERROR_INVALID_ARGUMENT, "Headphones already closed")
        return self._handle

    def is_initialized(self) -> bool:
        return bool(_dll.lib().mdrHeadphonesIsInitialized(self.handle))

    def is_ready(self) -> bool:
        return bool(_dll.lib().mdrHeadphonesIsReady(self.handle))

    def is_dirty(self) -> bool:
        return bool(_dll.lib().mdrHeadphonesIsDirty(self.handle))

    def request_init(self) -> int:
        return result.check(
            _dll.lib().mdrHeadphonesRequestInit(self.handle),
            allow_inprogress=True,
        )

    def request_fetch(self) -> int:
        return result.check(
            _dll.lib().mdrHeadphonesRequestFetch(self.handle),
            allow_inprogress=True,
        )

    def request_commit(self) -> int:
        return result.check(
            _dll.lib().mdrHeadphonesRequestCommit(self.handle),
            allow_inprogress=True,
        )

    def poll(self) -> int:
        event = c_uint32(constants.EVENT_NONE)
        result.check(_dll.lib().mdrHeadphonesPoll(self.handle, byref(event)))
        return int(event.value)

    def set_packet_callback(
        self,
        callback: Callable[[int, bytes], None] | None,
    ) -> None:
        lib = _dll.lib()
        if callback is None:
            lib.mdrHeadphonesSetPacketCallback(self.handle, _api.MDRPacketCallback(), None)
            self._packet_callback = None
            return

        def _trampoline(user_data, direction, frame, frame_size):  # noqa: ANN001
            raw = bytes(frame[:frame_size]) if frame and frame_size > 0 else b""
            callback(int(direction), raw)

        c_callback = _api.MDRPacketCallback(_trampoline)
        self._packet_callback = c_callback  # keep alive
        lib.mdrHeadphonesSetPacketCallback(self.handle, c_callback, None)

    def feature_availability(self, feature: int) -> int:
        availability = c_uint32(0)
        result.check(_dll.lib().mdrHeadphonesGetFeature(self.handle, feature, byref(availability)))
        return int(availability.value)

    def feature_available(self, feature: int) -> bool:
        return self.feature_availability(feature) == constants.AVAILABILITY_AVAILABLE

    def get_text(self, text_id: int, index: int = 0) -> str:
        lib = _dll.lib()
        size = c_uint32(0)
        code = lib.mdrHeadphonesGetText(self.handle, text_id, index, None, byref(size))
        if code != result.OK or size.value == 0:
            return ""
        buf = create_string_buffer(size.value)
        result.check(lib.mdrHeadphonesGetText(self.handle, text_id, index, buf, byref(size)))
        return buf.value.decode("utf-8", errors="replace")

    def get_model(self) -> _api.MDRModel:
        model = _api.MDRModel()
        result.check(_dll.lib().mdrHeadphonesGetModel(self.handle, byref(model)))
        return model

    def get_batteries(self) -> list[_api.MDRBattery]:
        lib = _dll.lib()
        count = c_uint32(0)
        result.check(lib.mdrHeadphonesGetBatteries(self.handle, None, byref(count)))
        if count.value == 0:
            return []
        array = (_api.MDRBattery * count.value)()
        result.check(lib.mdrHeadphonesGetBatteries(self.handle, array, byref(count)))
        return [array[i] for i in range(count.value)]

    def get_playback(self) -> _api.MDRPlayback:
        playback = _api.MDRPlayback()
        result.check(_dll.lib().mdrHeadphonesGetPlayback(self.handle, byref(playback)))
        return playback

    def get_noise_control(self) -> _api.MDRNoiseControl:
        noise = _api.MDRNoiseControl()
        result.check(_dll.lib().mdrHeadphonesGetNoiseControl(self.handle, byref(noise)))
        return noise

    def set_noise_control(self, noise: _api.MDRNoiseControl) -> None:
        result.check(_dll.lib().mdrHeadphonesSetNoiseControl(self.handle, byref(noise)))

    def cycle_noise_mode(self) -> int:
        noise = self.get_noise_control()
        order = (
            constants.NOISE_MODE_OFF,
            constants.NOISE_MODE_CANCELLING,
            constants.NOISE_MODE_AMBIENT,
        )
        try:
            index = order.index(int(noise.mode))
        except ValueError:
            index = 0
        noise.mode = order[(index + 1) % len(order)]
        self.set_noise_control(noise)
        return int(noise.mode)
