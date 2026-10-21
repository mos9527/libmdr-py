"""High-level wrapper around MDRHeadphones."""

from __future__ import annotations

from ctypes import byref, c_int32, c_uint32, c_void_p, create_string_buffer
from typing import TYPE_CHECKING

from . import _api, _dll, constants, result
from .connection import Connection

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


class PairedDevice:
    def __init__(
        self,
        name: str,
        address: str,
        connected: bool,
        playback: bool,
    ) -> None:
        self.name = name
        self.address = address
        self.connected = connected
        self.playback = playback


class Headphones:
    def __init__(
        self,
        connection: Connection,
        *,
        abi_version: int = result.ABI_VERSION,
        protocol_version: int = constants.PROTOCOL_V2,
    ) -> None:
        """Open a session against the connected headphones.

        ``protocol_version`` must match the MDR service the connection was
        established against: :data:`constants.PROTOCOL_V2` for XM5+ (and every
        BLE device) or :data:`constants.PROTOCOL_V1` for legacy models. It
        defaults to ``PROTOCOL_V2`` since that is the modern/common case.
        """
        handle = c_void_p()
        result.check(
            _dll.lib().mdrHeadphonesCreate(
                abi_version,
                connection.pointer,
                protocol_version,
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

    def request_init(self, flags: int = constants.HEADPHONES_INIT_DEFAULT) -> int:
        """Request initialization of the parts selected by ``flags``.

        ``flags`` is any combination of ``constants.HEADPHONES_INIT_*``; use
        ``HEADPHONES_INIT_DISCOVERY`` to only identify the device. Optional parts
        require ``HEADPHONES_INIT_DISCOVERY`` either in ``flags`` or from an
        earlier call.
        """
        return result.check(
            _dll.lib().mdrHeadphonesRequestInit(self.handle, flags),
            allow_inprogress=True,
        )

    def request_sync(self, flags: int = constants.HEADPHONES_SYNC_DEFAULT) -> int:
        """Request pulling the states selected by ``flags``.

        ``flags`` is any combination of ``constants.HEADPHONES_SYNC_*``. After
        ``EVENT_NEED_SYNC``, pass :meth:`get_sync`.
        """
        return result.check(
            _dll.lib().mdrHeadphonesRequestSync(self.handle, flags),
            allow_inprogress=True,
        )

    def get_sync(self) -> int:
        """``HEADPHONES_SYNC_*`` flags marked stale by ``EVENT_NEED_SYNC``."""
        flags = c_uint32(constants.HEADPHONES_SYNC_NONE)
        result.check(_dll.lib().mdrHeadphonesGetSync(self.handle, byref(flags)))
        return int(flags.value)

    def request_commit(self) -> int:
        return result.check(
            _dll.lib().mdrHeadphonesRequestCommit(self.handle),
            allow_inprogress=True,
        )

    def poll(self) -> int:
        """Poll for the next event.

        Raises :class:`result.MDRError` on fatal failures, after which the
        instance stays failed: close it and create a new one.
        """
        event = c_uint32(constants.EVENT_NONE)
        result.check(_dll.lib().mdrHeadphonesPoll(self.handle, byref(event)))
        return int(event.value)

    def set_timeout(self, timeout_type: int, value: int) -> None:
        """Set a positive timeout in milliseconds, or an ACK retry count.

        ``timeout_type`` is ``constants.TIMEOUT_DEFAULT``,
        ``constants.TIMEOUT_ACK``, or ``constants.TIMEOUT_ACK_RETRIES``.
        """
        result.check(_dll.lib().mdrHeadphonesSetTimeout(self.handle, timeout_type, value))

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

    def get_playback(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDRPlayback:
        """Playback status and volume; ``view`` selects the volume view."""
        playback = _api.MDRPlayback()
        result.check(_dll.lib().mdrHeadphonesGetPlayback(self.handle, view, byref(playback)))
        return playback

    def set_volume(self, volume: int) -> None:
        """Stage a playback volume (clamped to 0..30)."""
        result.check(
            _dll.lib().mdrHeadphonesSetPlaybackVolume(self.handle, max(0, min(30, int(volume))))
        )

    def playback_command(self, action: int) -> None:
        """Stage a playback command; replaces any uncommitted command."""
        command = _api.MDRPlaybackCommand(action=action)
        result.check(_dll.lib().mdrHeadphonesSendPlaybackCommand(self.handle, byref(command)))

    def play(self) -> None:
        self.playback_command(constants.PLAYBACK_PLAY)

    def pause(self) -> None:
        self.playback_command(constants.PLAYBACK_PAUSE)

    def next_track(self) -> None:
        self.playback_command(constants.PLAYBACK_NEXT)

    def previous_track(self) -> None:
        self.playback_command(constants.PLAYBACK_PREVIOUS)

    def toggle_playback(self) -> None:
        if int(self.get_playback().status) == constants.PLAYBACK_PLAYING:
            self.pause()
        else:
            self.play()

    def get_noise_control(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDRNoiseControl:
        noise = _api.MDRNoiseControl()
        result.check(_dll.lib().mdrHeadphonesGetNoiseControl(self.handle, view, byref(noise)))
        return noise

    def set_noise_control(self, noise: _api.MDRNoiseControl) -> None:
        result.check(_dll.lib().mdrHeadphonesSetNoiseControl(self.handle, byref(noise)))

    def cycle_noise_mode(self) -> int:
        noise = self.get_noise_control(constants.PROPERTY_DESIRED)
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

    def get_speak_to_chat(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDRSpeakToChat:
        value = _api.MDRSpeakToChat()
        result.check(_dll.lib().mdrHeadphonesGetSpeakToChat(self.handle, view, byref(value)))
        return value

    def set_speak_to_chat(self, value: _api.MDRSpeakToChat) -> None:
        result.check(_dll.lib().mdrHeadphonesSetSpeakToChat(self.handle, byref(value)))

    def get_listening(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDRListening:
        value = _api.MDRListening()
        result.check(_dll.lib().mdrHeadphonesGetListening(self.handle, view, byref(value)))
        return value

    def set_listening(self, value: _api.MDRListening) -> None:
        result.check(_dll.lib().mdrHeadphonesSetListening(self.handle, byref(value)))

    def get_equalizer(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDREqualizer:
        value = _api.MDREqualizer()
        result.check(_dll.lib().mdrHeadphonesGetEqualizer(self.handle, view, byref(value)))
        return value

    def set_equalizer_preset(self, preset: int) -> None:
        """Stage an equalizer preset; see :meth:`get_equalizer_presets`."""
        result.check(_dll.lib().mdrHeadphonesSetEqualizerPreset(self.handle, preset))

    def set_equalizer_clear_bass(self, clear_bass: int) -> None:
        """Stage the Clear Bass level (-10..10)."""
        result.check(_dll.lib().mdrHeadphonesSetEqualizerClearBass(self.handle, int(clear_bass)))

    def set_dsee(self, enabled: bool) -> None:
        result.check(
            _dll.lib().mdrHeadphonesSetDSEE(
                self.handle,
                constants.TRUE if enabled else constants.FALSE,
            )
        )

    def get_equalizer_bands(self, view: int = constants.PROPERTY_CURRENT) -> list[int]:
        lib = _dll.lib()
        count = c_uint32(0)
        result.check(lib.mdrHeadphonesGetEqualizerBands(self.handle, view, None, byref(count)))
        if count.value == 0:
            return []
        array = (c_int32 * count.value)()
        result.check(lib.mdrHeadphonesGetEqualizerBands(self.handle, view, array, byref(count)))
        return [int(array[i]) for i in range(count.value)]

    def set_equalizer_bands(self, bands: Sequence[int]) -> None:
        """Stage band gains: five bands accept -10..10, ten accept -6..6."""
        count = len(bands)
        array = (c_int32 * count)(*(int(v) for v in bands))
        result.check(_dll.lib().mdrHeadphonesSetEqualizerBands(self.handle, array, count))

    def get_equalizer_presets(self) -> list[int]:
        """Presets the device advertised, in its order.

        An empty list means the device did not report one, in which case
        :meth:`set_equalizer_preset` accepts any preset.
        """
        lib = _dll.lib()
        count = c_uint32(0)
        result.check(lib.mdrHeadphonesGetEqualizerPresets(self.handle, None, byref(count)))
        if count.value == 0:
            return []
        array = (_api.MDREqualizerPreset * count.value)()
        result.check(lib.mdrHeadphonesGetEqualizerPresets(self.handle, array, byref(count)))
        return [int(array[i]) for i in range(count.value)]

    def get_paired_devices(self) -> list[PairedDevice]:
        lib = _dll.lib()
        count = c_uint32(0)
        result.check(lib.mdrHeadphonesGetPairedDevices(self.handle, None, byref(count)))
        if count.value == 0:
            return []
        array = (_api.MDRPairedDevice * count.value)()
        result.check(lib.mdrHeadphonesGetPairedDevices(self.handle, array, byref(count)))
        out: list[PairedDevice] = []
        for d in array:
            name = d.name.decode("utf-8", errors="replace").rstrip("\x00") or "(unknown)"
            address = d.macAddress.decode("utf-8", errors="replace").rstrip("\x00")
            out.append(
                PairedDevice(
                    name=name,
                    address=address,
                    connected=bool(int(d.connected)),
                    playback=bool(int(d.playback_device)),
                )
            )
        return out

    def set_paired_device(self, command: int, device_id: str) -> None:
        raw = device_id.encode("utf-8")
        action = _api.MDRPairedDeviceAction(
            command=command,
            device_id=raw,
            device_id_size=len(raw),
        )
        result.check(
            _dll.lib().mdrHeadphonesSetPairedDevice(self.handle, byref(action)),
            allow_inprogress=True,
        )

    def get_pairing(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDRPairing:
        value = _api.MDRPairing()
        result.check(_dll.lib().mdrHeadphonesGetPairing(self.handle, view, byref(value)))
        return value

    def set_pairing(self, enabled: bool) -> None:
        value = _api.MDRPairing(enabled=constants.TRUE if enabled else constants.FALSE)
        result.check(_dll.lib().mdrHeadphonesSetPairing(self.handle, byref(value)))

    def get_source_switch_control(self, view: int = constants.PROPERTY_CURRENT) -> bool:
        enabled = _api.MDRBoolean()
        result.check(
            _dll.lib().mdrHeadphonesGetSourceSwitchControl(self.handle, view, byref(enabled))
        )
        return bool(enabled.value)

    def set_source_switch_control(self, enabled: bool) -> None:
        result.check(
            _dll.lib().mdrHeadphonesSetSourceSwitchControl(
                self.handle,
                constants.TRUE if enabled else constants.FALSE,
            )
        )

    def get_source_switch_control_result(self) -> int:
        value = _api.MDRSourceSwitchControlResult()
        result.check(
            _dll.lib().mdrHeadphonesGetSourceSwitchControlResult(self.handle, byref(value))
        )
        return int(value.value)

    def set_alert_response(self, action: int) -> None:
        """Stage the answer to the confirmation asked for with ``EVENT_ALERT``.

        Sent on :meth:`request_commit`; a new response replaces any uncommitted
        one. Raises ``ERROR_NOT_FOUND`` when the device has not asked anything.
        """
        result.check(_dll.lib().mdrHeadphonesSetAlertResponse(self.handle, action))

    def get_general_setting_info(self) -> list[_api.MDRGeneralSettingInfo]:
        lib = _dll.lib()
        count = c_uint32(0)
        result.check(lib.mdrHeadphonesGetGeneralSettingInfo(self.handle, None, byref(count)))
        if count.value == 0:
            return []
        array = (_api.MDRGeneralSettingInfo * count.value)()
        result.check(lib.mdrHeadphonesGetGeneralSettingInfo(self.handle, array, byref(count)))
        return [array[i] for i in range(count.value)]

    def get_general_setting(
        self, index: int, view: int = constants.PROPERTY_CURRENT
    ) -> _api.MDRGeneralSetting:
        value = _api.MDRGeneralSetting()
        result.check(
            _dll.lib().mdrHeadphonesGetGeneralSetting(self.handle, view, index, byref(value))
        )
        return value

    def set_general_setting(self, index: int, enabled: bool) -> None:
        value = _api.MDRGeneralSetting(
            index=index,
            boolean_value=constants.TRUE if enabled else constants.FALSE,
        )
        result.check(_dll.lib().mdrHeadphonesSetGeneralSetting(self.handle, byref(value)))

    def general_setting_subject(self, index: int) -> str:
        return self.get_text(constants.TEXT_GENERAL_SETTING_SUBJECT, index)

    def general_setting_summary(self, index: int) -> str:
        return self.get_text(constants.TEXT_GENERAL_SETTING_SUMMARY, index)

    def equalizer_preset_name(self, index: int) -> str:
        """Name of the preset at ``index`` in :meth:`get_equalizer_presets`."""
        return self.get_text(constants.TEXT_EQUALIZER_PRESET_NAME, index)

    def get_assignable_controls(
        self, view: int = constants.PROPERTY_CURRENT
    ) -> list[_api.MDRAssignableControl]:
        lib = _dll.lib()
        count = c_uint32(0)
        result.check(
            lib.mdrHeadphonesGetAssignableControls(self.handle, view, None, byref(count))
        )
        if count.value == 0:
            return []
        array = (_api.MDRAssignableControl * count.value)()
        result.check(
            lib.mdrHeadphonesGetAssignableControls(self.handle, view, array, byref(count))
        )
        return [array[i] for i in range(count.value)]

    def get_assignable_control_actions(self, location: int) -> list[int]:
        """Actions the device offers for one key, e.g. ``ASSIGNABLE_ACTION_KEY_LEFT``."""
        lib = _dll.lib()
        count = c_uint32(0)
        result.check(
            lib.mdrHeadphonesGetAssignableControlActions(self.handle, location, None, byref(count))
        )
        if count.value == 0:
            return []
        array = (_api.MDRAssignableAction * count.value)()
        result.check(
            lib.mdrHeadphonesGetAssignableControlActions(
                self.handle, location, array, byref(count)
            )
        )
        return [int(array[i]) for i in range(count.value)]

    def set_assignable_controls(self, controls: Sequence[_api.MDRAssignableControl]) -> None:
        count = len(controls)
        if count == 0:
            return
        array = (_api.MDRAssignableControl * count)(*controls)
        result.check(_dll.lib().mdrHeadphonesSetAssignableControls(self.handle, array, count))

    def set_assignable_control(self, location: int, action: int, key_type: int = 0) -> None:
        """Assign ``action`` to one key, leaving the others untouched.

        ``key_type`` is only used when the device did not report that key.
        """
        controls = self.get_assignable_controls(constants.PROPERTY_DESIRED)
        for control in controls:
            if int(control.location) == location:
                control.action = action
                break
        else:
            controls.append(
                _api.MDRAssignableControl(location=location, type=key_type, action=action)
            )
        self.set_assignable_controls(controls)

    def get_power(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDRPower:
        value = _api.MDRPower()
        result.check(_dll.lib().mdrHeadphonesGetPower(self.handle, view, byref(value)))
        return value

    def set_power(self, value: _api.MDRPower) -> None:
        result.check(_dll.lib().mdrHeadphonesSetPower(self.handle, byref(value)))

    def shutdown(self) -> None:
        """Ask the device to power off (needs a commit to take effect)."""
        power = self.get_power(constants.PROPERTY_DESIRED)
        power.shutdown_requested = constants.TRUE
        self.set_power(power)

    def get_voice_guidance(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDRVoiceGuidance:
        value = _api.MDRVoiceGuidance()
        result.check(_dll.lib().mdrHeadphonesGetVoiceGuidance(self.handle, view, byref(value)))
        return value

    def set_voice_guidance(self, value: _api.MDRVoiceGuidance) -> None:
        result.check(_dll.lib().mdrHeadphonesSetVoiceGuidance(self.handle, byref(value)))

    def get_connection_mode(
        self, view: int = constants.PROPERTY_CURRENT
    ) -> _api.MDRConnectionMode:
        value = _api.MDRConnectionMode()
        result.check(_dll.lib().mdrHeadphonesGetConnectionMode(self.handle, view, byref(value)))
        return value

    def set_connection_mode(self, value: _api.MDRConnectionMode) -> None:
        result.check(_dll.lib().mdrHeadphonesSetConnectionMode(self.handle, byref(value)))

    def get_safe_listening(self, view: int = constants.PROPERTY_CURRENT) -> _api.MDRSafeListening:
        value = _api.MDRSafeListening()
        result.check(_dll.lib().mdrHeadphonesGetSafeListening(self.handle, view, byref(value)))
        return value

    def set_safe_listening(self, value: _api.MDRSafeListening) -> None:
        result.check(_dll.lib().mdrHeadphonesSetSafeListening(self.handle, byref(value)))

    def get_wearing_status(self) -> int:
        """Live proximity sensor reading. Requires ``FEATURE_WEARING_STATUS``."""
        value = _api.MDRWearingStatus()
        result.check(_dll.lib().mdrHeadphonesGetWearingStatus(self.handle, byref(value)))
        return int(value.value)
