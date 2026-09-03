"""Background worker that owns the MDR connection and poll loop.

All blocking C calls happen here, on a dedicated thread, so the GUI never
freezes.  Communication with the UI goes through Qt signals:

* output signals carry snapshots / status / log lines back to the main thread
* input signals (``req_*``) enqueue commands that ``run()`` executes on this
  thread.
"""

from __future__ import annotations

import queue
import time
from collections.abc import Callable

from libmdr import Headphones, constants as C, result
from libmdr_bt import create_connection

from .qt_compat import QThread, Signal, Slot

_PLAYBACK_ACTIONS = {
    "play": C.PLAYBACK_PLAY,
    "pause": C.PLAYBACK_PAUSE,
    "next": C.PLAYBACK_NEXT,
    "prev": C.PLAYBACK_PREVIOUS,
}


def _safe_text(hp, text_id: int, index: int = 0) -> str:
    try:
        return hp.get_text(text_id, index)
    except result.MDRError:
        return ""


def _safe(getter, default=None):
    try:
        return getter()
    except result.MDRError:
        return default


def take_snapshot(hp, previous=None, *, full: bool = False) -> dict:
    """Capture the full device state as a plain (cross-thread-safe) dict.

    ``full`` refreshes the slowly-changing fields (feature availability,
    general settings, paired devices).  Incremental updates keep those around
    from ``previous`` to avoid redundant C calls on every volume tweak.
    """
    snap = dict(previous) if previous else {}
    snap["ready"] = hp.is_ready()

    # --- identity / model -------------------------------------------------
    model = _safe(hp.get_model)
    if model is not None:
        snap["model"] = {
            "name": _safe_text(hp, C.TEXT_MODEL_NAME) or "未知型号",
            "series": _safe_text(hp, C.TEXT_MODEL_SERIES),
            "color": _safe_text(hp, C.TEXT_MODEL_COLOR),
            "firmware": _safe_text(hp, C.TEXT_FIRMWARE_VERSION),
            "protocol": int(model.protocol_version),
            "codec": C.AUDIO_CODEC_NAMES.get(int(model.audio_codec), "Unknown"),
            "unique_id": _safe_text(hp, C.TEXT_UNIQUE_ID),
        }
    else:
        snap["model"] = {}

    # --- batteries --------------------------------------------------------
    batteries = _safe(hp.get_batteries)
    if batteries is not None:
        snap["batteries"] = [
            {
                "part": C.BATTERY_PART_NAMES.get(int(b.part), f"part {b.part}"),
                "level": int(b.level_percent),
                "charging": C.CHARGING_NAMES.get(int(b.charging), "unknown"),
            }
            for b in batteries
            if int(b.present)
        ]
    else:
        snap["batteries"] = snap.get("batteries", [])

    # --- playback ---------------------------------------------------------
    playback = _safe(hp.get_playback)
    if playback is not None:
        meta = hp.feature_available(C.FEATURE_PLAYBACK_METADATA)
        snap["playback"] = {
            "status": C.PLAYBACK_STATUS_NAMES.get(int(playback.status), "Unknown"),
            "volume": int(playback.volume),
            "title": _safe_text(hp, C.TEXT_TRACK_TITLE) if meta else "",
            "artist": _safe_text(hp, C.TEXT_TRACK_ARTIST) if meta else "",
            "album": _safe_text(hp, C.TEXT_TRACK_ALBUM) if meta else "",
        }
    else:
        snap["playback"] = snap.get("playback", {})

    # --- noise control ----------------------------------------------------
    if hp.feature_available(C.FEATURE_NOISE_CANCELLING) or hp.feature_available(
        C.FEATURE_AMBIENT_SOUND
    ):
        noise = _safe(hp.get_noise_control)
        if noise is not None:
            snap["noise"] = {
                "mode": int(noise.mode),
                "ambient_level": int(noise.ambient_level),
                "focus_on_voice": bool(int(noise.focus_on_voice)),
                "button_mode": int(noise.button_mode),
                "adaptive_ambient": bool(int(noise.adaptive_ambient)),
                "adaptive_sensitivity": int(noise.adaptive_sensitivity),
                "has_nc": hp.feature_available(C.FEATURE_NOISE_CANCELLING),
                "has_ambient": hp.feature_available(C.FEATURE_AMBIENT_SOUND),
                "has_adaptive": hp.feature_available(C.FEATURE_ADAPTIVE_AMBIENT_SOUND),
                "has_button": hp.feature_available(C.FEATURE_NOISE_CONTROL_BUTTON),
            }
        else:
            snap.pop("noise", None)
    else:
        snap.pop("noise", None)

    # --- speak-to-chat ----------------------------------------------------
    if hp.feature_available(C.FEATURE_SPEAK_TO_CHAT):
        speak = _safe(hp.get_speak_to_chat)
        if speak is not None:
            snap["speak"] = {
                "enabled": bool(int(speak.enabled)),
                "sensitivity": int(speak.sensitivity),
                "timeout": int(speak.timeout),
            }
        else:
            snap.pop("speak", None)
    else:
        snap.pop("speak", None)

    # --- listening mode ---------------------------------------------------
    if hp.feature_available(C.FEATURE_LISTENING_MODE):
        listening = _safe(hp.get_listening)
        if listening is not None:
            snap["listening"] = {
                "mode": int(listening.mode),
                "room": int(listening.background_room),
            }
        else:
            snap.pop("listening", None)
    else:
        snap.pop("listening", None)

    # --- equalizer --------------------------------------------------------
    if hp.feature_available(C.FEATURE_EQUALIZER):
        eq = _safe(hp.get_equalizer)
        bands = _safe(hp.get_equalizer_bands)
        if eq is not None:
            snap["equalizer"] = {
                "preset": int(eq.preset),
                "clear_bass": int(eq.clear_bass),
                "band_count": int(eq.band_count),
                "bands": bands if bands is not None else [],
                "dsee_enabled": bool(int(eq.dsee_enabled)),
                "dsee_type": int(eq.dsee_type),
                "has_dsee": hp.feature_available(C.FEATURE_DSEE),
            }
        else:
            snap.pop("equalizer", None)
    else:
        snap.pop("equalizer", None)

    # --- voice guidance ---------------------------------------------------
    if hp.feature_available(C.FEATURE_VOICE_GUIDANCE):
        voice = _safe(hp.get_voice_guidance)
        if voice is not None:
            snap["voice"] = {
                "enabled": bool(int(voice.enabled)),
                "volume": int(voice.volume),
            }
        else:
            snap.pop("voice", None)
    else:
        snap.pop("voice", None)

    # --- connection mode --------------------------------------------------
    if hp.feature_available(C.FEATURE_CONNECTION_MODE):
        cm = _safe(hp.get_connection_mode)
        if cm is not None:
            snap["connection_mode"] = {"audio_priority": int(cm.audio_priority)}
        else:
            snap.pop("connection_mode", None)
    else:
        snap.pop("connection_mode", None)

    # --- safe listening ---------------------------------------------------
    if hp.feature_available(C.FEATURE_SAFE_LISTENING):
        sl = _safe(hp.get_safe_listening)
        if sl is not None:
            snap["safe_listening"] = {
                "sound_pressure": int(sl.sound_pressure),
                "preview": bool(int(sl.preview)),
            }
        else:
            snap.pop("safe_listening", None)
    else:
        snap.pop("safe_listening", None)

    # --- power ------------------------------------------------------------
    if any(
        hp.feature_available(f)
        for f in (
            C.FEATURE_AUTO_POWER_OFF,
            C.FEATURE_WEARING_DETECTION,
            C.FEATURE_AUTO_PAUSE,
            C.FEATURE_HEAD_GESTURE,
            C.FEATURE_SHUTDOWN,
        )
    ):
        power = _safe(hp.get_power)
        if power is not None:
            snap["power"] = {
                "auto_power_off_minutes": int(power.auto_power_off_minutes),
                "wearing_power": int(power.wearing_power),
                "auto_pause": bool(int(power.auto_pause)),
                "head_gesture": bool(int(power.head_gesture)),
                "has_apo": hp.feature_available(C.FEATURE_AUTO_POWER_OFF),
                "has_wearing": hp.feature_available(C.FEATURE_WEARING_DETECTION),
                "has_autopause": hp.feature_available(C.FEATURE_AUTO_PAUSE),
                "has_gesture": hp.feature_available(C.FEATURE_HEAD_GESTURE),
                "has_shutdown": hp.feature_available(C.FEATURE_SHUTDOWN),
            }
        else:
            snap.pop("power", None)
    else:
        snap.pop("power", None)

    # --- assignable controls ---------------------------------------------
    if hp.feature_available(C.FEATURE_ASSIGNABLE_CONTROLS):
        assign = _safe(hp.get_assignable_controls)
        if assign is not None:
            snap["assignable"] = {"left": int(assign.left), "right": int(assign.right)}
        else:
            snap.pop("assignable", None)
    else:
        snap.pop("assignable", None)

    # --- pairing mode -----------------------------------------------------
    if hp.feature_available(C.FEATURE_PAIRING_MODE):
        pr = _safe(hp.get_pairing)
        if pr is not None:
            snap["pairing"] = {"enabled": bool(int(pr.enabled))}
        else:
            snap.pop("pairing", None)
    else:
        snap.pop("pairing", None)

    # --- full-only fields -------------------------------------------------
    if full:
        snap["features"] = {
            fid: C.AVAILABILITY_NAMES.get(hp.feature_availability(fid), "unknown")
            for fid in C.FEATURE_NAMES
        }

        if hp.feature_available(C.FEATURE_GENERAL_SETTINGS):
            try:
                infos = hp.get_general_setting_info()
                gen = []
                for info in infos:
                    idx = int(info.index)
                    try:
                        g = hp.get_general_setting(idx)
                        value = bool(int(g.boolean_value))
                    except result.MDRError:
                        value = False
                    gen.append(
                        {
                            "index": idx,
                            "type": int(info.type),
                            "writable": bool(int(info.writable)),
                            "value": value,
                            "subject": hp.general_setting_subject(idx),
                            "summary": hp.general_setting_summary(idx),
                        }
                    )
                snap["general_settings"] = gen
            except result.MDRError:
                snap["general_settings"] = []
        else:
            snap["general_settings"] = []

        if hp.feature_available(C.FEATURE_PAIRED_DEVICE_MANAGEMENT):
            devices = _safe(hp.get_paired_devices)
            snap["paired_devices"] = [
                {
                    "name": d.name,
                    "address": d.address,
                    "connected": d.connected,
                    "playback": d.playback,
                }
                for d in (devices or [])
            ]
        else:
            snap["paired_devices"] = []
    else:
        snap.setdefault("features", {})
        snap.setdefault("general_settings", [])
        snap.setdefault("paired_devices", [])

    # --- latest device messages ------------------------------------------
    snap["messages"] = {
        "last_error": _safe_text(hp, C.TEXT_LAST_ERROR),
        "last_alert": _safe_text(hp, C.TEXT_LAST_ALERT),
        "last_interaction": _safe_text(hp, C.TEXT_LAST_INTERACTION),
        "last_device_message": _safe_text(hp, C.TEXT_LAST_DEVICE_MESSAGE),
    }
    return snap


class DeviceWorker(QThread):
    """Runs the MDR platform + headphones poll loop off the GUI thread."""

    # output
    backend_ready = Signal(str)
    devices_discovered = Signal(list)
    connection_state = Signal(str)
    state_updated = Signal(object)
    log_message = Signal(str)
    event_occurred = Signal(str)

    # input (UI -> worker, queued)
    req_connect = Signal(str)
    req_disconnect = Signal()
    req_scan = Signal()
    req_restart = Signal(bool)
    req_fetch = Signal()
    req_playback = Signal(str)
    req_volume = Signal(int)
    req_set = Signal(str, int)
    req_set_bool = Signal(str, bool)
    req_eq_band = Signal(int, int)
    req_paired = Signal(int, str)
    req_general = Signal(int, bool)

    def __init__(self, ble: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._ble = ble
        self._platform = None
        self._headphones = None
        self._last_snapshot = None
        self._commands: queue.Queue[tuple[Callable, tuple] | None] = queue.Queue()

        # A QThread object belongs to the thread that created it, so connecting
        # these signals directly to _on_* would execute all the blocking work
        # on the GUI thread. The signal handlers only enqueue commands; run()
        # executes them and owns every native MDR call.
        self.req_connect.connect(lambda address: self._submit(self._on_connect, address))
        self.req_disconnect.connect(lambda: self._submit(self._on_disconnect))
        self.req_scan.connect(lambda: self._submit(self._on_scan))
        self.req_restart.connect(lambda ble: self._submit(self._on_restart, ble))
        self.req_fetch.connect(lambda: self._submit(self._on_fetch))
        self.req_playback.connect(lambda action: self._submit(self._on_playback, action))
        self.req_volume.connect(lambda volume: self._submit(self._on_volume, volume))
        self.req_set.connect(lambda name, value: self._submit(self._on_set, name, value))
        self.req_set_bool.connect(
            lambda name, value: self._submit(self._on_set_bool, name, value)
        )
        self.req_eq_band.connect(
            lambda index, value: self._submit(self._on_eq_band, index, value)
        )
        self.req_paired.connect(
            lambda command, device_id: self._submit(self._on_paired, command, device_id)
        )
        self.req_general.connect(
            lambda index, value: self._submit(self._on_general, index, value)
        )

    def _submit(self, callback: Callable, *args: object) -> None:
        self._commands.put((callback, args))

    def quit(self) -> None:
        """Stop after commands already submitted by the UI have completed."""
        self._commands.put(None)

    # -- thread entry ------------------------------------------------------
    def run(self) -> None:
        try:
            self._platform = create_connection(ble=self._ble)
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit(f"无法创建平台连接：{exc}")
            self.connection_state.emit("failed")
            return

        self.backend_ready.emit(self._platform.backend)
        self._scan_emit()
        self.connection_state.emit("idle")
        try:
            while True:
                try:
                    command = self._commands.get(timeout=0.05)
                except queue.Empty:
                    self._tick()
                    continue

                if command is None:
                    break
                callback, args = command
                try:
                    callback(*args)
                except Exception as exc:  # noqa: BLE001
                    self.log_message.emit(f"工作线程错误：{exc}")
                self._tick()
        finally:
            self._teardown_connection()
            if self._platform is not None:
                try:
                    self._platform.close()
                except Exception:  # noqa: BLE001
                    pass
                self._platform = None

    # -- poll loop ---------------------------------------------------------
    def _tick(self) -> None:
        hp = self._headphones
        if hp is None:
            return

        try:
            while True:
                event = hp.poll()
                if event == C.EVENT_NONE:
                    break
                self._handle_event(event)
        except result.MDRError as exc:
            self.log_message.emit(f"设备轮询错误：{exc}（连接可能已断开）")
            self._teardown_connection()
            return

        try:
            if hp.is_ready() and hp.is_dirty():
                hp.request_commit()
        except result.MDRError as exc:
            self.log_message.emit(f"提交更改失败：{exc}")

    def _handle_event(self, event: int) -> None:
        self.event_occurred.emit(C.EVENT_NAMES.get(event, str(event)))

        if event == C.EVENT_INITIALIZE_COMPLETE:
            self.log_message.emit("初始化完成，正在获取设备状态…")
            try:
                self._headphones.request_fetch()
            except result.MDRError as exc:
                self.log_message.emit(f"获取状态失败：{exc}")
        elif event == C.EVENT_SYNC_COMPLETE:
            self.log_message.emit("设备状态已同步")
            self.connection_state.emit("connected")
            self._emit_state(full=True)
        elif event == C.EVENT_APPLY_COMPLETE:
            self._emit_state(full=False)
        elif event in (
            C.EVENT_BATTERY_CHANGED,
            C.EVENT_PLAYBACK_CHANGED,
            C.EVENT_NOISE_CONTROL_CHANGED,
            C.EVENT_SPEAK_TO_CHAT_CHANGED,
            C.EVENT_LISTENING_MODE_CHANGED,
            C.EVENT_EQUALIZER_CHANGED,
            C.EVENT_IDENTITY_CHANGED,
            C.EVENT_ASSIGNABLE_CONTROLS_CHANGED,
            C.EVENT_POWER_CHANGED,
            C.EVENT_VOICE_GUIDANCE_CHANGED,
            C.EVENT_CONNECTION_MODE_CHANGED,
            C.EVENT_SAFE_LISTENING_CHANGED,
        ):
            self._emit_state(full=False)
        elif event in (
            C.EVENT_PAIRED_DEVICES_CHANGED,
            C.EVENT_PAIRING_CHANGED,
            C.EVENT_GENERAL_SETTINGS_CHANGED,
        ):
            self._emit_state(full=True)
        elif event == C.EVENT_ALERT:
            self.log_message.emit(f"设备提醒：{_safe_text(self._headphones, C.TEXT_LAST_ALERT)}")
            self._emit_state(full=False)
        elif event == C.EVENT_INTERACTION:
            self.log_message.emit(f"交互事件：{_safe_text(self._headphones, C.TEXT_LAST_INTERACTION)}")
        elif event == C.EVENT_DEVICE_MESSAGE:
            self.log_message.emit(f"设备消息：{_safe_text(self._headphones, C.TEXT_LAST_DEVICE_MESSAGE)}")

    def _emit_state(self, *, full: bool = False) -> None:
        if self._headphones is None:
            return
        try:
            snap = take_snapshot(self._headphones, self._last_snapshot, full=full)
            self._last_snapshot = snap
            self.state_updated.emit(snap)
        except result.MDRError as exc:
            self.log_message.emit(f"读取状态失败：{exc}")

    def _scan_emit(self) -> None:
        if self._platform is None:
            return
        try:
            devices = self._platform.devices()
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit(f"扫描设备失败：{exc}")
            return
        self.devices_discovered.emit([(d.name, d.address) for d in devices])
        self.log_message.emit(f"发现 {len(devices)} 台设备")

    def _teardown_connection(self) -> None:
        had_connection = self._headphones is not None
        if had_connection:
            try:
                self._headphones.close()
            except Exception:  # noqa: BLE001
                pass
            self._headphones = None
        self._last_snapshot = None
        self.connection_state.emit("disconnected" if had_connection else "idle")
        self.state_updated.emit(None)

    # -- input slots -------------------------------------------------------
    @Slot(str)
    def _on_connect(self, address: str) -> None:
        if not address or self._platform is None:
            return
        self.connection_state.emit("connecting")
        self.event_occurred.emit("connecting")
        self.log_message.emit(f"正在连接 {address} …")

        services = (
            [result.BLE_SERVICE_UUID_TANDEM_OVER_BLE_HPC]
            if self._ble
            else [result.SERVICE_UUID_XM5, result.SERVICE_UUID_LEGACY]
        )
        connected = False
        last_error = ""
        for service in services:
            try:
                self._platform.disconnect()
            except Exception:  # noqa: BLE001
                pass
            try:
                code = self._platform.connect(address, service)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                continue
            if code not in (result.OK, result.INPROGRESS):
                last_error = self._platform.last_error() or f"connect={code}"
                continue

            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                poll = self._platform.poll(0)
                if poll == result.OK:
                    connected = True
                    break
                if poll not in (result.INPROGRESS, result.ERROR_TIMEOUT):
                    last_error = self._platform.last_error() or f"poll={poll}"
                    break
                time.sleep(0.01)
            if connected:
                break
            last_error = self._platform.last_error() or last_error or "timeout"

        if not connected:
            self.connection_state.emit("failed")
            self.log_message.emit(f"连接失败（{address}）：{last_error}")
            return

        try:
            self._headphones = Headphones(self._platform.connection)
            self._headphones.request_init()
            self._last_snapshot = None
        except result.MDRError as exc:
            self.log_message.emit(f"初始化耳机失败：{exc}")
            self.connection_state.emit("failed")
            return
        self.log_message.emit("已连接，正在初始化设备…")

    @Slot()
    def _on_disconnect(self) -> None:
        if self._platform is not None:
            try:
                self._platform.disconnect()
            except Exception as exc:  # noqa: BLE001
                self.log_message.emit(f"断开时出错：{exc}")
        self._teardown_connection()

    @Slot()
    def _on_scan(self) -> None:
        self._scan_emit()

    @Slot(bool)
    def _on_restart(self, ble: bool) -> None:
        self._teardown_connection()
        if self._platform is not None:
            try:
                self._platform.close()
            except Exception:  # noqa: BLE001
                pass

        self._ble = ble
        try:
            self._platform = create_connection(ble=ble)
        except Exception as exc:  # noqa: BLE001
            self.log_message.emit(f"重建连接失败：{exc}")
            self.connection_state.emit("failed")
            return
        self.backend_ready.emit(self._platform.backend)
        self._scan_emit()
        self.connection_state.emit("idle")

    @Slot()
    def _on_fetch(self) -> None:
        if self._headphones is None:
            return
        try:
            self._headphones.request_fetch()
        except result.MDRError as exc:
            self.log_message.emit(f"刷新状态失败：{exc}")

    @Slot(str)
    def _on_playback(self, action: str) -> None:
        hp = self._headphones
        if hp is None:
            return
        try:
            if action == "toggle":
                hp.toggle_playback()
            elif action in _PLAYBACK_ACTIONS:
                hp.playback_command(_PLAYBACK_ACTIONS[action])
        except result.MDRError as exc:
            self.log_message.emit(f"播放命令失败：{exc}")

    @Slot(int)
    def _on_volume(self, volume: int) -> None:
        if self._headphones is None:
            return
        try:
            self._headphones.set_volume(volume)
        except result.MDRError as exc:
            self.log_message.emit(f"设置音量失败：{exc}")

    @Slot(str, int)
    def _on_set(self, name: str, value: int) -> None:
        hp = self._headphones
        if hp is None:
            return
        try:
            if name == "noise_mode":
                n = hp.get_noise_control()
                n.mode = value
                hp.set_noise_control(n)
            elif name == "noise_ambient":
                n = hp.get_noise_control()
                n.ambient_level = value
                hp.set_noise_control(n)
            elif name == "noise_voice":
                n = hp.get_noise_control()
                n.focus_on_voice = value
                hp.set_noise_control(n)
            elif name == "noise_adaptive":
                n = hp.get_noise_control()
                n.adaptive_ambient = value
                hp.set_noise_control(n)
            elif name == "noise_sensitivity":
                n = hp.get_noise_control()
                n.adaptive_sensitivity = value
                hp.set_noise_control(n)
            elif name == "noise_button":
                n = hp.get_noise_control()
                n.button_mode = value
                hp.set_noise_control(n)
            elif name == "stc_sensitivity":
                s = hp.get_speak_to_chat()
                s.sensitivity = value
                hp.set_speak_to_chat(s)
            elif name == "stc_timeout":
                s = hp.get_speak_to_chat()
                s.timeout = value
                hp.set_speak_to_chat(s)
            elif name == "listening_mode":
                l = hp.get_listening()
                l.mode = value
                hp.set_listening(l)
            elif name == "listening_room":
                l = hp.get_listening()
                l.background_room = value
                hp.set_listening(l)
            elif name == "eq_preset":
                e = hp.get_equalizer()
                e.preset = value
                hp.set_equalizer(e)
            elif name == "eq_bass":
                e = hp.get_equalizer()
                e.clear_bass = value
                hp.set_equalizer(e)
            elif name == "eq_dsee":
                e = hp.get_equalizer()
                e.dsee_enabled = value
                hp.set_equalizer(e)
            elif name == "power_apo":
                p = hp.get_power()
                p.auto_power_off_minutes = value
                hp.set_power(p)
            elif name == "power_wearing":
                p = hp.get_power()
                p.wearing_power = value
                hp.set_power(p)
            elif name == "assign_left":
                a = hp.get_assignable_controls()
                a.left = value
                hp.set_assignable_controls(a)
            elif name == "assign_right":
                a = hp.get_assignable_controls()
                a.right = value
                hp.set_assignable_controls(a)
            elif name == "conn_priority":
                cm = hp.get_connection_mode()
                cm.audio_priority = value
                hp.set_connection_mode(cm)
            elif name == "safe_preview":
                sl = hp.get_safe_listening()
                sl.preview = value
                hp.set_safe_listening(sl)
            elif name == "power_shutdown":
                p = hp.get_power()
                p.shutdown_requested = value
                hp.set_power(p)
        except result.MDRError as exc:
            self.log_message.emit(f"设置 {name} 失败：{exc}")

    @Slot(str, bool)
    def _on_set_bool(self, name: str, value: bool) -> None:
        hp = self._headphones
        if hp is None:
            return
        try:
            if name == "stc_enabled":
                s = hp.get_speak_to_chat()
                s.enabled = value
                hp.set_speak_to_chat(s)
            elif name == "power_autopause":
                p = hp.get_power()
                p.auto_pause = value
                hp.set_power(p)
            elif name == "power_gesture":
                p = hp.get_power()
                p.head_gesture = value
                hp.set_power(p)
            elif name == "voice_enabled":
                v = hp.get_voice_guidance()
                v.enabled = value
                hp.set_voice_guidance(v)
            elif name == "pairing":
                pr = hp.get_pairing()
                pr.enabled = value
                hp.set_pairing(pr)
        except result.MDRError as exc:
            self.log_message.emit(f"设置 {name} 失败：{exc}")

    @Slot(int, int)
    def _on_eq_band(self, index: int, value: int) -> None:
        hp = self._headphones
        if hp is None:
            return
        try:
            bands = hp.get_equalizer_bands()
            if 0 <= index < len(bands):
                bands[index] = value
                hp.set_equalizer_bands(bands)
        except result.MDRError as exc:
            self.log_message.emit(f"设置 EQ 频段失败：{exc}")

    @Slot(int, str)
    def _on_paired(self, command: int, device_id: str) -> None:
        if self._headphones is None:
            return
        try:
            self._headphones.set_paired_device(command, device_id)
        except result.MDRError as exc:
            self.log_message.emit(f"配对设备操作失败：{exc}")

    @Slot(int, bool)
    def _on_general(self, index: int, value: bool) -> None:
        if self._headphones is None:
            return
        try:
            self._headphones.set_general_setting(index, value)
        except result.MDRError as exc:
            self.log_message.emit(f"通用设置失败：{exc}")
