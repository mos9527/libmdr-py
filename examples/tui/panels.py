"""Feature panels for the libmdr TUI.

Each panel mirrors one tab of the reference SonyHeadphonesClient GUI and talks
to a :class:`libmdr.Headphones` instance directly.  Panels are *stateless*: on
every ``sync()`` they read the current device state and push it into their
widgets, and every widget interaction writes straight back to the device.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Collapsible,
    DataTable,
    Label,
    Select,
    Static,
    Switch,
)

from libmdr import constants, result

from .widgets import EnumSelect, Slider

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.widget import Widget

    from libmdr import Headphones

C = constants

VOLUME_RANGE = (0, 30)
AMBIENT_RANGE = (1, 20)
CLEAR_BASS_RANGE = (-10, 10)
VOICE_GUIDANCE_VOLUME_RANGE = (-2, 2)
MAX_GENERAL_SETTINGS = 8
MAX_EQUALIZER_BANDS = 10


def _options(names: dict[int, str], keys: tuple[int, ...]) -> list[tuple[str, int]]:
    return [(names.get(key, str(key)), key) for key in keys]


NOISE_MODE_OPTIONS = {
    C.NOISE_MODE_OFF: "Off",
    C.NOISE_MODE_CANCELLING: "Noise Cancelling",
    C.NOISE_MODE_AMBIENT: "Ambient Sound",
}

ADAPTIVE_SENSITIVITY_OPTIONS = _options(
    C.ADAPTIVE_SENSITIVITY_NAMES,
    (C.ADAPTIVE_SENSITIVITY_LOW, C.ADAPTIVE_SENSITIVITY_STANDARD, C.ADAPTIVE_SENSITIVITY_HIGH),
)
NOISE_BUTTON_OPTIONS = _options(
    C.NOISE_BUTTON_NAMES,
    (
        C.NOISE_BUTTON_NONE,
        C.NOISE_BUTTON_NOISE_AMBIENT_OFF,
        C.NOISE_BUTTON_NOISE_AMBIENT,
        C.NOISE_BUTTON_NOISE_OFF,
        C.NOISE_BUTTON_AMBIENT_OFF,
    ),
)
SPEECH_SENSITIVITY_OPTIONS = _options(
    C.SPEECH_SENSITIVITY_NAMES,
    (C.SPEECH_SENSITIVITY_AUTO, C.SPEECH_SENSITIVITY_LOW, C.SPEECH_SENSITIVITY_HIGH),
)
SPEAK_TIMEOUT_OPTIONS = _options(
    C.SPEAK_TIMEOUT_NAMES,
    (
        C.SPEAK_TIMEOUT_SHORT,
        C.SPEAK_TIMEOUT_MEDIUM,
        C.SPEAK_TIMEOUT_LONG,
        C.SPEAK_TIMEOUT_MANUAL,
    ),
)
LISTENING_OPTIONS = _options(
    C.LISTENING_MODE_NAMES,
    (C.LISTENING_STANDARD, C.LISTENING_BACKGROUND_MUSIC, C.LISTENING_CINEMA),
)
ROOM_OPTIONS = _options(C.ROOM_SIZE_NAMES, (C.ROOM_SMALL, C.ROOM_MEDIUM, C.ROOM_LARGE))
EQUALIZER_OPTIONS = [
    (name, preset)
    for preset, name in C.EQUALIZER_PRESET_NAMES.items()
    if preset != C.EQ_UNKNOWN
]
AUTO_POWER_OFF_OPTIONS = [
    (C.AUTO_POWER_OFF_NAMES[value], value) for value in C.AUTO_POWER_OFF_CHOICES
]
WEARING_POWER_OPTIONS = _options(
    C.WEARING_POWER_NAMES, (C.WEARING_POWER_DISABLED, C.WEARING_POWER_WHEN_REMOVED)
)
ASSIGNABLE_OPTIONS = _options(
    C.ASSIGNABLE_ACTION_NAMES,
    (
        C.ASSIGNABLE_NONE,
        C.ASSIGNABLE_PLAYBACK,
        C.ASSIGNABLE_NOISE_CONTROL,
        C.ASSIGNABLE_NOISE_CONTROL_QUICK_ACCESS,
        C.ASSIGNABLE_TRACK_CONTROL,
        C.ASSIGNABLE_VOICE_ASSISTANT,
        C.ASSIGNABLE_QUICK_ACCESS,
    ),
)
AUDIO_PRIORITY_OPTIONS = _options(
    C.AUDIO_PRIORITY_NAMES, (C.AUDIO_PRIORITY_QUALITY, C.AUDIO_PRIORITY_STABILITY)
)

FEATURE_ORDER = tuple(sorted(C.FEATURE_NAMES))


def row(label: str, widget: Widget, *, classes: str = "setting-row") -> Horizontal:
    return Horizontal(Label(label, classes="setting-label"), widget, classes=classes)


def _flag(value: object) -> bool:
    return bool(int(value))


class Panel(VerticalScroll):
    """Base class holding the shared ``Headphones`` reference."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.hp: Headphones | None = None

    def attach(self, headphones: Headphones | None) -> None:
        self.hp = headphones
        self.invalidate()
        self.sync()

    def invalidate(self) -> None:
        """Drop cached signatures so the next sync rebuilds dynamic content."""

    @property
    def device(self) -> Headphones | None:
        hp = self.hp
        if hp is None:
            return None
        try:
            if not hp.is_ready():
                return None
        except result.MDRError:
            return None
        return hp

    def report(self, message: str) -> None:
        log_line = getattr(self.app, "log_line", None)
        if callable(log_line):
            log_line(message)

    def available(self, feature: int) -> bool:
        hp = self.hp
        if hp is None:
            return False
        try:
            return hp.feature_available(feature)
        except result.MDRError:
            return False

    def sync(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def set_enabled(self, selector: str, enabled: bool) -> None:
        for widget in self.query(selector):
            widget.disabled = not enabled


class PlaybackPanel(Panel):
    def compose(self) -> ComposeResult:
        yield Static("", id="pb_track", classes="card")
        with Horizontal(classes="button-row"):
            yield Button("\u23ee  Prev", id="pb_prev")
            yield Button("\u23ef  Play / Pause", id="pb_toggle", variant="primary")
            yield Button("\u23ed  Next", id="pb_next")
        yield row("Volume", Slider(*VOLUME_RANGE, 0, id="pb_volume"))

    def sync(self) -> None:
        track = self.query_one("#pb_track", Static)
        hp = self.device
        if hp is None:
            track.update("[dim]Not connected.[/dim]")
            self.set_enabled("#pb_prev, #pb_toggle, #pb_next, #pb_volume", False)
            return

        metadata = self.available(C.FEATURE_PLAYBACK_METADATA)
        controllable = self.available(C.FEATURE_PLAYBACK_CONTROL)
        has_volume = self.available(C.FEATURE_PLAYBACK_VOLUME)

        try:
            playback = hp.get_playback()
            status = C.PLAYBACK_STATUS_NAMES.get(int(playback.status), "Unknown")
            if metadata:
                title = hp.get_text(C.TEXT_TRACK_TITLE) or "(no title)"
                album = hp.get_text(C.TEXT_TRACK_ALBUM) or "(no album)"
                artist = hp.get_text(C.TEXT_TRACK_ARTIST) or "(no artist)"
                track.update(
                    f"[b]{title}[/b]\n"
                    f"[dim]{artist} — {album}[/dim]\n"
                    f"Status: [cyan]{status}[/cyan]   Volume: [cyan]{playback.volume}[/cyan]"
                )
            else:
                track.update(
                    f"[dim]Playback metadata unavailable.[/dim]\n"
                    f"Status: [cyan]{status}[/cyan]   Volume: [cyan]{playback.volume}[/cyan]"
                )
            slider = self.query_one("#pb_volume", Slider)
            slider.set_value(int(playback.volume))
        except result.MDRError as exc:
            track.update(f"[red]{exc}[/red]")

        self.set_enabled("#pb_prev, #pb_toggle, #pb_next", controllable)
        self.set_enabled("#pb_volume", has_volume)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        hp = self.device
        if hp is None:
            return
        event.stop()
        actions = {
            "pb_prev": hp.previous_track,
            "pb_toggle": hp.toggle_playback,
            "pb_next": hp.next_track,
        }
        action = actions.get(event.button.id or "")
        if action is None:
            return
        try:
            action()
        except result.MDRError as exc:
            self.report(f"[red]playback:[/red] {exc}")

    def on_slider_changed(self, event: Slider.Changed) -> None:
        hp = self.device
        if hp is None or event.slider.id != "pb_volume":
            return
        event.stop()
        try:
            if int(hp.get_playback().volume) != event.value:
                hp.set_volume(event.value)
        except result.MDRError as exc:
            self.report(f"[red]volume:[/red] {exc}")


class SoundPanel(Panel):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._band_count = -1

    def invalidate(self) -> None:
        self._band_count = -1

    def compose(self) -> ComposeResult:
        with Collapsible(title="Noise control", collapsed=False):
            yield row("Mode", EnumSelect(id="nc_mode"))
            yield row("Ambient level", Slider(*AMBIENT_RANGE, 1, id="nc_ambient"))
            yield row("Focus on voice", Switch(id="nc_voice"))
            yield row("Adaptive ambient", Switch(id="nc_adaptive"))
            yield row("Adaptive sensitivity", EnumSelect(ADAPTIVE_SENSITIVITY_OPTIONS, id="nc_sens"))
            yield row("Button behaviour", EnumSelect(NOISE_BUTTON_OPTIONS, id="nc_button"))
        with Collapsible(title="Speak-to-chat", collapsed=False):
            yield row("Enabled", Switch(id="stc_enabled"))
            yield row("Sensitivity", EnumSelect(SPEECH_SENSITIVITY_OPTIONS, id="stc_sens"))
            yield row("Auto off timer", EnumSelect(SPEAK_TIMEOUT_OPTIONS, id="stc_timeout"))
        with Collapsible(title="Listening mode", collapsed=False):
            yield row("Mode", EnumSelect(LISTENING_OPTIONS, id="lm_mode"))
            yield row("Background room", EnumSelect(ROOM_OPTIONS, id="lm_room"))
        with Collapsible(title="Equalizer", collapsed=False):
            yield row("Preset", EnumSelect(EQUALIZER_OPTIONS, id="eq_preset"))
            yield row("Clear bass", Slider(*CLEAR_BASS_RANGE, 0, id="eq_bass"))
            with Vertical(id="eq_bands"):
                for index in range(MAX_EQUALIZER_BANDS):
                    yield Horizontal(
                        Label("", id=f"eq_label_{index}", classes="band-label"),
                        Slider(-10, 10, 0, id=f"eq_band_{index}"),
                        classes="band-row",
                    )
            yield row("DSEE", Switch(id="eq_dsee"))
            yield Static("", id="eq_dsee_type", classes="hint")

    def sync(self) -> None:
        hp = self.device
        if hp is None:
            for widget in self.query("Switch, Slider, Select"):
                widget.disabled = True
            return
        self._sync_noise(hp)
        self._sync_speak_to_chat(hp)
        self._sync_listening(hp)
        self._sync_equalizer(hp)

    # -- noise control ---------------------------------------------------

    def _sync_noise(self, hp: Headphones) -> None:
        nc_available = self.available(C.FEATURE_NOISE_CANCELLING)
        amb_available = self.available(C.FEATURE_AMBIENT_SOUND)
        adaptive = self.available(C.FEATURE_ADAPTIVE_AMBIENT_SOUND)
        button = self.available(C.FEATURE_NOISE_CONTROL_BUTTON)

        modes: list[tuple[str, int]] = [(NOISE_MODE_OPTIONS[C.NOISE_MODE_OFF], C.NOISE_MODE_OFF)]
        if nc_available:
            modes.append((NOISE_MODE_OPTIONS[C.NOISE_MODE_CANCELLING], C.NOISE_MODE_CANCELLING))
        if amb_available:
            modes.append((NOISE_MODE_OPTIONS[C.NOISE_MODE_AMBIENT], C.NOISE_MODE_AMBIENT))

        mode_select = self.query_one("#nc_mode", EnumSelect)
        mode_select.update_options(modes)

        enabled = nc_available or amb_available
        mode_select.disabled = not enabled
        self.set_enabled("#nc_ambient, #nc_voice", amb_available)
        self.set_enabled("#nc_adaptive, #nc_sens", adaptive)
        self.set_enabled("#nc_button", button)
        if not enabled:
            return

        try:
            noise = hp.get_noise_control()
        except result.MDRError:
            return
        mode_select.select_value(int(noise.mode))
        self.query_one("#nc_ambient", Slider).set_value(int(noise.ambient_level))
        self.query_one("#nc_voice", Switch).value = _flag(noise.focus_on_voice)
        self.query_one("#nc_adaptive", Switch).value = _flag(noise.adaptive_ambient)
        self.query_one("#nc_sens", EnumSelect).select_value(int(noise.adaptive_sensitivity))
        self.query_one("#nc_button", EnumSelect).select_value(int(noise.button_mode))

    # -- speak to chat ---------------------------------------------------

    def _sync_speak_to_chat(self, hp: Headphones) -> None:
        available = self.available(C.FEATURE_SPEAK_TO_CHAT)
        self.set_enabled("#stc_enabled, #stc_sens, #stc_timeout", available)
        if not available:
            return
        try:
            stc = hp.get_speak_to_chat()
        except result.MDRError:
            return
        self.query_one("#stc_enabled", Switch).value = _flag(stc.enabled)
        self.query_one("#stc_sens", EnumSelect).select_value(int(stc.sensitivity))
        self.query_one("#stc_timeout", EnumSelect).select_value(int(stc.timeout))

    # -- listening -------------------------------------------------------

    def _sync_listening(self, hp: Headphones) -> None:
        available = self.available(C.FEATURE_LISTENING_MODE)
        self.set_enabled("#lm_mode, #lm_room", available)
        if not available:
            return
        try:
            listening = hp.get_listening()
        except result.MDRError:
            return
        self.query_one("#lm_mode", EnumSelect).select_value(int(listening.mode))
        room = self.query_one("#lm_room", EnumSelect)
        room.select_value(int(listening.background_room))
        room.disabled = int(listening.mode) != C.LISTENING_BACKGROUND_MUSIC

    # -- equalizer -------------------------------------------------------

    def _sync_equalizer(self, hp: Headphones) -> None:
        eq_available = self.available(C.FEATURE_EQUALIZER)
        dsee_available = self.available(C.FEATURE_DSEE)
        self.set_enabled("#eq_preset, #eq_bass", eq_available)
        self.set_enabled("#eq_dsee", dsee_available)

        if not (eq_available or dsee_available):
            for index in range(MAX_EQUALIZER_BANDS):
                self.query_one(f"#eq_band_{index}").parent.display = False
            return

        try:
            equalizer = hp.get_equalizer()
        except result.MDRError:
            return

        if eq_available:
            self.query_one("#eq_preset", EnumSelect).select_value(int(equalizer.preset))
            self.query_one("#eq_bass", Slider).set_value(int(equalizer.clear_bass))

        band_count = int(equalizer.band_count) if eq_available else 0
        labels = C.EQUALIZER_BAND_LABELS.get(band_count, ())
        low, high = C.EQUALIZER_BAND_RANGE.get(band_count, CLEAR_BASS_RANGE)
        try:
            bands = hp.get_equalizer_bands() if band_count else []
        except result.MDRError:
            bands = []

        for index in range(MAX_EQUALIZER_BANDS):
            slider = self.query_one(f"#eq_band_{index}", Slider)
            container = slider.parent
            visible = index < band_count
            if container is not None:
                container.display = visible
            if not visible:
                continue
            label = labels[index] if index < len(labels) else f"B{index + 1}"
            self.query_one(f"#eq_label_{index}", Label).update(f"{label} Hz")
            slider.set_range(low, high)
            if index < len(bands):
                slider.set_value(bands[index])

        if dsee_available:
            self.query_one("#eq_dsee", Switch).value = _flag(equalizer.dsee_enabled)
            name = C.DSEE_TYPE_NAMES.get(int(equalizer.dsee_type), "DSEE")
            self.query_one("#eq_dsee_type", Static).update(f"[dim]Upscaling engine: {name}[/dim]")
        else:
            self.query_one("#eq_dsee_type", Static).update("")

    # -- handlers --------------------------------------------------------

    def on_select_changed(self, event: Select.Changed) -> None:
        hp = self.device
        if hp is None or event.value is Select.BLANK:
            return
        event.stop()
        widget_id = event.select.id
        value = int(event.value)
        try:
            if widget_id in {"nc_mode", "nc_sens", "nc_button"}:
                noise = hp.get_noise_control()
                field = {
                    "nc_mode": "mode",
                    "nc_sens": "adaptive_sensitivity",
                    "nc_button": "button_mode",
                }[widget_id]
                if int(getattr(noise, field)) == value:
                    return
                setattr(noise, field, value)
                hp.set_noise_control(noise)
            elif widget_id in {"stc_sens", "stc_timeout"}:
                stc = hp.get_speak_to_chat()
                field = "sensitivity" if widget_id == "stc_sens" else "timeout"
                if int(getattr(stc, field)) == value:
                    return
                setattr(stc, field, value)
                hp.set_speak_to_chat(stc)
            elif widget_id in {"lm_mode", "lm_room"}:
                listening = hp.get_listening()
                field = "mode" if widget_id == "lm_mode" else "background_room"
                if int(getattr(listening, field)) == value:
                    return
                setattr(listening, field, value)
                hp.set_listening(listening)
            elif widget_id == "eq_preset":
                equalizer = hp.get_equalizer()
                if int(equalizer.preset) == value:
                    return
                equalizer.preset = value
                hp.set_equalizer(equalizer)
        except result.MDRError as exc:
            self.report(f"[red]{widget_id}:[/red] {exc}")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        hp = self.device
        if hp is None:
            return
        event.stop()
        widget_id = event.switch.id
        value = event.value
        try:
            if widget_id in {"nc_voice", "nc_adaptive"}:
                noise = hp.get_noise_control()
                field = "focus_on_voice" if widget_id == "nc_voice" else "adaptive_ambient"
                if _flag(getattr(noise, field)) == value:
                    return
                setattr(noise, field, C.TRUE if value else C.FALSE)
                hp.set_noise_control(noise)
            elif widget_id == "stc_enabled":
                stc = hp.get_speak_to_chat()
                if _flag(stc.enabled) == value:
                    return
                stc.enabled = C.TRUE if value else C.FALSE
                hp.set_speak_to_chat(stc)
            elif widget_id == "eq_dsee":
                equalizer = hp.get_equalizer()
                if _flag(equalizer.dsee_enabled) == value:
                    return
                equalizer.dsee_enabled = C.TRUE if value else C.FALSE
                hp.set_equalizer(equalizer)
        except result.MDRError as exc:
            self.report(f"[red]{widget_id}:[/red] {exc}")

    def on_slider_changed(self, event: Slider.Changed) -> None:
        hp = self.device
        if hp is None:
            return
        event.stop()
        widget_id = event.slider.id or ""
        value = event.value
        try:
            if widget_id == "nc_ambient":
                noise = hp.get_noise_control()
                if int(noise.ambient_level) == value:
                    return
                noise.ambient_level = value
                hp.set_noise_control(noise)
            elif widget_id == "eq_bass":
                equalizer = hp.get_equalizer()
                if int(equalizer.clear_bass) == value:
                    return
                equalizer.clear_bass = value
                hp.set_equalizer(equalizer)
            elif widget_id.startswith("eq_band_"):
                index = int(widget_id.rsplit("_", 1)[1])
                bands = hp.get_equalizer_bands()
                if index >= len(bands) or bands[index] == value:
                    return
                bands[index] = value
                hp.set_equalizer_bands(bands)
        except result.MDRError as exc:
            self.report(f"[red]{widget_id}:[/red] {exc}")


class DevicesPanel(Panel):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._signature: tuple[tuple[str, str, bool, bool], ...] | None = None
        self._ids: list[str] = []

    def invalidate(self) -> None:
        self._signature = None
        self._ids = []

    def compose(self) -> ComposeResult:
        yield row("Pairing mode", Switch(id="dev_pairing"))
        yield Static(
            "[dim]Enable pairing mode to make the headphones discoverable.[/dim]",
            classes="hint",
        )
        yield DataTable(id="dev_table", cursor_type="row", zebra_stripes=True)
        with Horizontal(classes="button-row"):
            yield Button("Connect", id="dev_connect", variant="primary")
            yield Button("Disconnect", id="dev_disconnect")
            yield Button("Set playback", id="dev_playback")
            yield Button("Unpair", id="dev_unpair", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#dev_table", DataTable)
        table.add_columns("Name", "Address", "Status")

    def sync(self) -> None:
        hp = self.device
        available = hp is not None and self.available(C.FEATURE_PAIRED_DEVICE_MANAGEMENT)
        pairing = hp is not None and self.available(C.FEATURE_PAIRING_MODE)
        self.set_enabled("#dev_pairing", pairing)
        self.set_enabled(
            "#dev_connect, #dev_disconnect, #dev_playback, #dev_unpair", bool(available)
        )

        if hp is None:
            if self._signature is not None:
                self.query_one("#dev_table", DataTable).clear()
                self._signature = None
                self._ids = []
            return

        if pairing:
            try:
                self.query_one("#dev_pairing", Switch).value = _flag(hp.get_pairing().enabled)
            except result.MDRError:
                pass

        if not available:
            return

        try:
            devices = hp.get_paired_devices()
            rows = []
            ids = []
            for device in devices:
                rows.append(
                    (device.name, device.address, _flag(device.connected), _flag(device.playback))
                )
                ids.append(device.address)
        except result.MDRError as exc:
            self.report(f"[red]paired devices:[/red] {exc}")
            return

        signature = tuple(rows)
        if signature == self._signature:
            return

        table = self.query_one("#dev_table", DataTable)
        cursor = table.cursor_row
        table.clear()
        for name, address, connected, playback in rows:
            status = "connected" if connected else "paired"
            if playback:
                status += " · playback"
            table.add_row(name, address, status)
        self._signature = signature
        self._ids = ids
        if rows:
            table.move_cursor(row=min(cursor if cursor is not None else 0, len(rows) - 1))

    def _selected_id(self) -> str | None:
        table = self.query_one("#dev_table", DataTable)
        index = table.cursor_row
        if index is None or not (0 <= index < len(self._ids)):
            return None
        return self._ids[index]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        hp = self.device
        if hp is None:
            return
        event.stop()
        commands = {
            "dev_connect": C.PAIRED_DEVICE_CONNECT,
            "dev_disconnect": C.PAIRED_DEVICE_DISCONNECT,
            "dev_playback": C.PAIRED_DEVICE_SELECT_PLAYBACK,
            "dev_unpair": C.PAIRED_DEVICE_UNPAIR,
        }
        command = commands.get(event.button.id or "")
        if command is None:
            return
        device_id = self._selected_id()
        if not device_id:
            self.report("[yellow]Select a paired device first[/yellow]")
            return
        try:
            hp.set_paired_device(command, device_id)
            self.report(
                f"{C.PAIRED_DEVICE_COMMAND_NAMES[command]} \u2192 [cyan]{device_id}[/cyan]"
            )
        except result.MDRError as exc:
            self.report(f"[red]paired device:[/red] {exc}")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        hp = self.device
        if hp is None or event.switch.id != "dev_pairing":
            return
        event.stop()
        try:
            if _flag(hp.get_pairing().enabled) != event.value:
                hp.set_pairing(event.value)
        except result.MDRError as exc:
            self.report(f"[red]pairing:[/red] {exc}")


class SystemPanel(Panel):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._general_ids: list[int] = []
        self._general_signature: tuple[tuple[int, str, str, bool], ...] | None = None

    def invalidate(self) -> None:
        self._general_ids = []
        self._general_signature = None

    def compose(self) -> ComposeResult:
        with Collapsible(title="Power", collapsed=False):
            yield row("Auto power off", EnumSelect(AUTO_POWER_OFF_OPTIONS, id="sys_apo"))
            yield row("Wearing detection", EnumSelect(WEARING_POWER_OPTIONS, id="sys_wearing"))
            yield row("Pause when removed", Switch(id="sys_autopause"))
            yield row("Head gesture", Switch(id="sys_gesture"))
            with Horizontal(classes="button-row"):
                yield Button("Power off headphones", id="sys_shutdown", variant="error")
        with Collapsible(title="Voice guidance", collapsed=False):
            yield row("Enabled", Switch(id="sys_vg"))
            yield row("Volume", Slider(*VOICE_GUIDANCE_VOLUME_RANGE, 0, id="sys_vg_volume"))
        with Collapsible(title="Touch sensor", collapsed=False):
            yield row("Left", EnumSelect(ASSIGNABLE_OPTIONS, id="sys_left"))
            yield row("Right", EnumSelect(ASSIGNABLE_OPTIONS, id="sys_right"))
        with Collapsible(title="Connection", collapsed=False):
            yield row("Audio priority", EnumSelect(AUDIO_PRIORITY_OPTIONS, id="sys_priority"))
        with Collapsible(title="Safe listening", collapsed=False):
            yield Static("", id="sys_safe_info", classes="hint")
            yield row("Preview", Switch(id="sys_safe_preview"))
        with Collapsible(title="Other settings", collapsed=False):
            with Vertical(id="sys_general"):
                for index in range(MAX_GENERAL_SETTINGS):
                    yield Horizontal(
                        Label("", id=f"gs_label_{index}", classes="setting-label"),
                        Switch(id=f"gs_switch_{index}"),
                        classes="setting-row",
                    )
                    yield Static("", id=f"gs_hint_{index}", classes="hint")
            yield Static("", id="sys_general_empty", classes="hint")

    def sync(self) -> None:
        hp = self.device
        if hp is None:
            for widget in self.query("Switch, Slider, Select, Button"):
                widget.disabled = True
            return
        self._sync_power(hp)
        self._sync_voice_guidance(hp)
        self._sync_assignable(hp)
        self._sync_connection(hp)
        self._sync_safe_listening(hp)
        self._sync_general(hp)

    def _sync_power(self, hp: Headphones) -> None:
        apo = self.available(C.FEATURE_AUTO_POWER_OFF)
        wearing = self.available(C.FEATURE_WEARING_DETECTION)
        auto_pause = self.available(C.FEATURE_AUTO_PAUSE)
        gesture = self.available(C.FEATURE_HEAD_GESTURE)
        shutdown = self.available(C.FEATURE_SHUTDOWN)

        self.set_enabled("#sys_apo", apo)
        self.set_enabled("#sys_wearing", wearing)
        self.set_enabled("#sys_autopause", auto_pause)
        self.set_enabled("#sys_gesture", gesture)
        self.set_enabled("#sys_shutdown", shutdown)

        try:
            power = hp.get_power()
        except result.MDRError:
            return
        minutes = int(power.auto_power_off_minutes)
        select = self.query_one("#sys_apo", EnumSelect)
        options = list(AUTO_POWER_OFF_OPTIONS)
        if minutes not in C.AUTO_POWER_OFF_CHOICES:
            options.append((f"{minutes} minutes", minutes))
        select.update_options(options)
        select.select_value(minutes)
        self.query_one("#sys_wearing", EnumSelect).select_value(int(power.wearing_power))
        self.query_one("#sys_autopause", Switch).value = _flag(power.auto_pause)
        self.query_one("#sys_gesture", Switch).value = _flag(power.head_gesture)

    def _sync_voice_guidance(self, hp: Headphones) -> None:
        available = self.available(C.FEATURE_VOICE_GUIDANCE)
        volume = self.available(C.FEATURE_VOICE_GUIDANCE_VOLUME)
        self.set_enabled("#sys_vg", available)
        self.set_enabled("#sys_vg_volume", volume)
        if not (available or volume):
            return
        try:
            guidance = hp.get_voice_guidance()
        except result.MDRError:
            return
        self.query_one("#sys_vg", Switch).value = _flag(guidance.enabled)
        self.query_one("#sys_vg_volume", Slider).set_value(int(guidance.volume))

    def _sync_assignable(self, hp: Headphones) -> None:
        available = self.available(C.FEATURE_ASSIGNABLE_CONTROLS)
        self.set_enabled("#sys_left, #sys_right", available)
        if not available:
            return
        try:
            controls = hp.get_assignable_controls()
        except result.MDRError:
            return
        self.query_one("#sys_left", EnumSelect).select_value(int(controls.left))
        self.query_one("#sys_right", EnumSelect).select_value(int(controls.right))

    def _sync_connection(self, hp: Headphones) -> None:
        available = self.available(C.FEATURE_CONNECTION_MODE)
        self.set_enabled("#sys_priority", available)
        if not available:
            return
        try:
            mode = hp.get_connection_mode()
        except result.MDRError:
            return
        self.query_one("#sys_priority", EnumSelect).select_value(int(mode.audio_priority))

    def _sync_safe_listening(self, hp: Headphones) -> None:
        available = self.available(C.FEATURE_SAFE_LISTENING)
        info = self.query_one("#sys_safe_info", Static)
        self.set_enabled("#sys_safe_preview", available)
        if not available:
            info.update("[dim]Safe listening is not supported by this device.[/dim]")
            return
        try:
            safe = hp.get_safe_listening()
        except result.MDRError:
            return
        info.update(f"[dim]Current sound pressure: {int(safe.sound_pressure)} dB[/dim]")
        self.query_one("#sys_safe_preview", Switch).value = _flag(safe.preview)

    def _sync_general(self, hp: Headphones) -> None:
        available = self.available(C.FEATURE_GENERAL_SETTINGS)
        empty = self.query_one("#sys_general_empty", Static)
        if not available:
            for index in range(MAX_GENERAL_SETTINGS):
                self.query_one(f"#gs_switch_{index}").parent.display = False
                self.query_one(f"#gs_hint_{index}", Static).display = False
            empty.update("[dim]No additional settings reported by this device.[/dim]")
            self._general_signature = ()
            self._general_ids = []
            return

        try:
            infos = hp.get_general_setting_info()
            entries: list[tuple[int, str, str, bool]] = []
            for info in infos:
                if int(info.type) != C.GENERAL_SETTING_BOOLEAN:
                    continue
                index = int(info.index)
                entries.append(
                    (
                        index,
                        hp.general_setting_subject(index) or f"Setting {index}",
                        hp.general_setting_summary(index),
                        _flag(info.writable),
                    )
                )
        except result.MDRError:
            return

        entries = entries[:MAX_GENERAL_SETTINGS]
        empty.update("" if entries else "[dim]No additional settings reported.[/dim]")

        signature = tuple(entries)
        rebuild = signature != self._general_signature
        if rebuild:
            self._general_signature = signature
            self._general_ids = [entry[0] for entry in entries]

        for slot in range(MAX_GENERAL_SETTINGS):
            switch = self.query_one(f"#gs_switch_{slot}", Switch)
            container = switch.parent
            hint = self.query_one(f"#gs_hint_{slot}", Static)
            visible = slot < len(entries)
            if container is not None:
                container.display = visible
            hint.display = visible
            if not visible:
                continue
            index, subject, summary, writable = entries[slot]
            if rebuild:
                self.query_one(f"#gs_label_{slot}", Label).update(subject)
                hint.update(f"[dim]{summary}[/dim]" if summary else "")
            switch.disabled = not writable
            try:
                switch.value = _flag(hp.get_general_setting(index).boolean_value)
            except result.MDRError:
                pass

    # -- handlers --------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        hp = self.device
        if hp is None or event.button.id != "sys_shutdown":
            return
        event.stop()
        try:
            hp.shutdown()
            self.report("[yellow]Shutdown requested[/yellow]")
        except result.MDRError as exc:
            self.report(f"[red]shutdown:[/red] {exc}")

    def on_select_changed(self, event: Select.Changed) -> None:
        hp = self.device
        if hp is None or event.value is Select.BLANK:
            return
        event.stop()
        widget_id = event.select.id
        value = int(event.value)
        try:
            if widget_id in {"sys_apo", "sys_wearing"}:
                power = hp.get_power()
                field = "auto_power_off_minutes" if widget_id == "sys_apo" else "wearing_power"
                if int(getattr(power, field)) == value:
                    return
                setattr(power, field, value)
                hp.set_power(power)
            elif widget_id in {"sys_left", "sys_right"}:
                controls = hp.get_assignable_controls()
                field = "left" if widget_id == "sys_left" else "right"
                if int(getattr(controls, field)) == value:
                    return
                setattr(controls, field, value)
                hp.set_assignable_controls(controls)
            elif widget_id == "sys_priority":
                mode = hp.get_connection_mode()
                if int(mode.audio_priority) == value:
                    return
                mode.audio_priority = value
                hp.set_connection_mode(mode)
        except result.MDRError as exc:
            self.report(f"[red]{widget_id}:[/red] {exc}")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        hp = self.device
        if hp is None:
            return
        event.stop()
        widget_id = event.switch.id or ""
        value = event.value
        try:
            if widget_id in {"sys_autopause", "sys_gesture"}:
                power = hp.get_power()
                field = "auto_pause" if widget_id == "sys_autopause" else "head_gesture"
                if _flag(getattr(power, field)) == value:
                    return
                setattr(power, field, C.TRUE if value else C.FALSE)
                hp.set_power(power)
            elif widget_id == "sys_vg":
                guidance = hp.get_voice_guidance()
                if _flag(guidance.enabled) == value:
                    return
                guidance.enabled = C.TRUE if value else C.FALSE
                hp.set_voice_guidance(guidance)
            elif widget_id == "sys_safe_preview":
                safe = hp.get_safe_listening()
                if _flag(safe.preview) == value:
                    return
                safe.preview = C.TRUE if value else C.FALSE
                hp.set_safe_listening(safe)
            elif widget_id.startswith("gs_switch_"):
                slot = int(widget_id.rsplit("_", 1)[1])
                if slot >= len(self._general_ids):
                    return
                index = self._general_ids[slot]
                if _flag(hp.get_general_setting(index).boolean_value) == value:
                    return
                hp.set_general_setting(index, value)
        except result.MDRError as exc:
            self.report(f"[red]{widget_id}:[/red] {exc}")

    def on_slider_changed(self, event: Slider.Changed) -> None:
        hp = self.device
        if hp is None or event.slider.id != "sys_vg_volume":
            return
        event.stop()
        try:
            guidance = hp.get_voice_guidance()
            if int(guidance.volume) == event.value:
                return
            guidance.volume = event.value
            hp.set_voice_guidance(guidance)
        except result.MDRError as exc:
            self.report(f"[red]voice guidance:[/red] {exc}")


class AboutPanel(Panel):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._features: tuple[int, ...] = ()

    def invalidate(self) -> None:
        self._features = ()

    def compose(self) -> ComposeResult:
        yield Static("", id="about_info", classes="card")
        yield Static("Capabilities", classes="section-title")
        yield DataTable(id="about_features", cursor_type="row", zebra_stripes=True)
        yield Static("Device messages", classes="section-title")
        yield Static("", id="about_messages", classes="card")

    def on_mount(self) -> None:
        table = self.query_one("#about_features", DataTable)
        table.add_columns("Capability", "Status")

    def sync(self) -> None:
        info = self.query_one("#about_info", Static)
        messages = self.query_one("#about_messages", Static)
        hp = self.hp
        if hp is None:
            info.update("[dim]Not connected.[/dim]")
            messages.update("")
            if self._features:
                self.query_one("#about_features", DataTable).clear()
                self._features = ()
            return

        try:
            model = hp.get_model()
            info.update(
                f"[b]{hp.get_text(C.TEXT_MODEL_NAME) or '(unknown model)'}[/b]\n"
                f"Series: {hp.get_text(C.TEXT_MODEL_SERIES) or 'n/a'}   "
                f"Colour: {hp.get_text(C.TEXT_MODEL_COLOR) or 'n/a'}\n"
                f"Firmware: {hp.get_text(C.TEXT_FIRMWARE_VERSION) or 'n/a'}   "
                f"Protocol: v{int(model.protocol_version)}\n"
                f"Codec: {C.AUDIO_CODEC_NAMES.get(int(model.audio_codec), 'Unknown')}\n"
                f"Unique ID: {hp.get_text(C.TEXT_UNIQUE_ID) or 'n/a'}"
            )
            messages.update(
                f"[b]Last error[/b] {hp.get_text(C.TEXT_LAST_ERROR) or '-'}\n"
                f"[b]Last alert[/b] {hp.get_text(C.TEXT_LAST_ALERT) or '-'}\n"
                f"[b]Last interaction[/b] {hp.get_text(C.TEXT_LAST_INTERACTION) or '-'}\n"
                f"[b]Last message[/b] {hp.get_text(C.TEXT_LAST_DEVICE_MESSAGE) or '-'}"
            )
        except result.MDRError as exc:
            info.update(f"[red]{exc}[/red]")
            return

        try:
            states = tuple(hp.feature_availability(feature) for feature in FEATURE_ORDER)
        except result.MDRError:
            return
        if states == self._features:
            return
        self._features = states

        table = self.query_one("#about_features", DataTable)
        table.clear()
        for feature, state in zip(FEATURE_ORDER, states):
            name = C.FEATURE_NAMES.get(feature, str(feature))
            if state == C.AVAILABILITY_AVAILABLE:
                status = "[green]available[/green]"
            elif state == C.AVAILABILITY_UNAVAILABLE:
                status = "[red]unavailable[/red]"
            else:
                status = "[dim]unknown[/dim]"
            table.add_row(name, status)
