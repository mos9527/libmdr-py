"""Full-featured Textual TUI for libmdr / libmdr-bt.

This mirrors the feature set of the reference SonyHeadphonesClient GUI:
playback control, noise control, speak-to-chat, listening modes, equalizer,
paired device management, system/power settings and a capability overview.

Install:
  pip install -e libmdr[bt]  (or: -e libmdr -e libmdr-bt)
  pip install -r examples/requirements.txt

Run:
  python -m examples.tui

Optional env overrides:
  MDR_DLL              path to mdr-shared (or mdr.dll)
  MDR_BT_DLL           path to mdr-bt-shared.dll
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Allow `python examples/tui/app.py` from the repo root without installing examples.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from examples.tui.panels import (
    AboutPanel,
    DevicesPanel,
    PlaybackPanel,
    SoundPanel,
    SystemPanel,
    row,
)
from libmdr import Headphones, constants, result
from libmdr.connection import DeviceInfo
from libmdr_bt import PlatformConnection, create_connection

C = constants

STATUS_INTERVAL = 5
SYNC_INTERVAL = 20


def _battery_text(headphones: Headphones) -> str:
    try:
        batteries = headphones.get_batteries()
    except result.MDRError:
        return "[dim]battery n/a[/dim]"
    parts = []
    for battery in batteries:
        if not battery.present or not battery.update_threshold_percent:
            continue
        name = C.BATTERY_PART_NAMES.get(int(battery.part), f"part{battery.part}")
        level = int(battery.level_percent)
        filled = max(0, min(10, round(level / 10)))
        bar = "█" * filled + "░" * (10 - filled)
        colour = "green" if level > 40 else ("yellow" if level > 15 else "red")
        suffix = {
            C.CHARGING_YES: " [cyan]⚡[/cyan]",
            C.CHARGING_COMPLETE: " [green]✓[/green]",
        }.get(int(battery.charging), "")
        parts.append(f"{name} [{colour}]{bar}[/{colour}] {level:3d}%{suffix}")
    return "   ".join(parts) if parts else "[dim]no battery reported[/dim]"


class DeviceListItem(ListItem):
    def __init__(self, device: DeviceInfo) -> None:
        super().__init__(Label(f"{device.name}\n[dim]{device.address}[/dim]"))
        self.device = device


class StatusPanel(Static):
    def show_idle(self, backend: str, message: str = "") -> None:
        self.update(
            f"[b]Backend[/b] {backend}    [b]State[/b] [yellow]disconnected[/yellow]\n{message}"
        )

    def show_connecting(self, device: DeviceInfo, detail: str) -> None:
        self.update(
            f"[b]{device.name}[/b]  [dim]{device.address}[/dim]\n"
            f"[b]State[/b] [yellow]connecting…[/yellow]  {detail}"
        )

    def show_connected(self, headphones: Headphones, last_event: str) -> None:
        model = headphones.get_text(C.TEXT_MODEL_NAME) or "(unknown model)"
        firmware = headphones.get_text(C.TEXT_FIRMWARE_VERSION) or "n/a"
        codec = "n/a"
        try:
            codec = C.AUDIO_CODEC_NAMES.get(
                int(headphones.get_model().audio_codec), "Unknown"
            )
        except result.MDRError:
            pass

        noise = "n/a"
        try:
            if headphones.feature_available(
                C.FEATURE_NOISE_CANCELLING
            ) or headphones.feature_available(C.FEATURE_AMBIENT_SOUND):
                state = headphones.get_noise_control()
                noise = C.NOISE_MODE_NAMES.get(int(state.mode), str(state.mode))
                if int(state.mode) == C.NOISE_MODE_AMBIENT:
                    noise += f" ({state.ambient_level})"
        except result.MDRError:
            pass

        playing = "n/a"
        try:
            playback = headphones.get_playback()
            playing = C.PLAYBACK_STATUS_NAMES.get(int(playback.status), "Unknown")
            playing += f"  vol {int(playback.volume)}"
        except result.MDRError:
            pass

        ready = "[green]ready[/green]" if headphones.is_ready() else "[yellow]syncing[/yellow]"
        dirty = " [magenta]•dirty[/magenta]" if headphones.is_dirty() else ""

        self.update(
            f"[b]{model}[/b]  [dim]fw {firmware}[/dim]  [cyan]{codec}[/cyan]  {ready}{dirty}\n"
            f"{_battery_text(headphones)}\n"
            f"[b]ANC[/b] {noise}    [b]Playback[/b] {playing}    "
            f"[b]Event[/b] [magenta]{last_event}[/magenta]"
        )


class HeadphonesTui(App[None]):
    CSS = """
    Screen { layout: vertical; }

    #body { height: 1fr; }

    #sidebar {
        width: 34;
        border: round $accent;
        padding: 0 1;
    }
    #sidebar.-hidden { display: none; }
    #devices { height: 1fr; }
    #toolbar { height: auto; padding: 1 0 0 0; }
    #toolbar Button { width: 1fr; min-width: 8; }

    #main { width: 1fr; }
    #status {
        height: 5;
        border: round $primary;
        padding: 0 1;
    }

    TabbedContent { height: 1fr; }
    TabPane { padding: 0 1; }

    Panel { height: 1fr; }

    .setting-row { height: 3; width: 1fr; align: left middle; }
    .setting-label { width: 26; height: 3; content-align: left middle; }
    .band-row { height: 1; width: 1fr; align: left middle; }
    .band-label { width: 10; height: 1; content-align: right middle; color: $text-muted; }
    .button-row { height: auto; padding: 1 0; }
    .button-row Button { margin: 0 1 0 0; }
    .card {
        padding: 1;
        border: round $primary-darken-1;
        height: auto;
    }
    .hint { padding: 0 0 1 26; color: $text-muted; height: auto; }
    .section-title { padding: 1 0 0 0; text-style: bold; }

    Collapsible { border: none; padding: 0; }

    #dev_table { height: 12; }
    #about_features { height: 22; }

    #log_pane { height: 1fr; }
    #log { height: 1fr; border: round $primary-darken-1; }
    """

    TITLE = "libmdr"
    SUB_TITLE = "Sony headphones control"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Scan"),
        Binding("c", "connect", "Connect"),
        Binding("d", "disconnect", "Disconnect"),
        Binding("n", "cycle_noise", "Cycle ANC"),
        Binding("f", "fetch", "Fetch"),
        Binding("b", "toggle_ble", "BLE"),
        Binding("s", "toggle_sidebar", "Sidebar"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._ble = False
        self._platform: PlatformConnection | None = None
        self._headphones: Headphones | None = None
        self._selected: DeviceInfo | None = None
        self._last_event = "none"
        self._connecting = False
        self._ticks = 0
        self._packet_log = False

    # -- composition -----------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("[b]Bluetooth devices[/b]")
                yield ListView(id="devices")
                with Vertical(id="toolbar"):
                    with Horizontal():
                        yield Button("Scan", id="btn_refresh")
                        yield Button("Connect", id="btn_connect", variant="primary")
                    with Horizontal():
                        yield Button("Disconnect", id="btn_disconnect")
                        yield Button("BLE: off", id="btn_ble")
            with Vertical(id="main"):
                yield StatusPanel(id="status")
                with TabbedContent(id="tabs"):
                    with TabPane("Playback", id="tab_playback"):
                        yield PlaybackPanel(id="panel_playback")
                    with TabPane("Sound", id="tab_sound"):
                        yield SoundPanel(id="panel_sound")
                    with TabPane("Devices", id="tab_devices"):
                        yield DevicesPanel(id="panel_devices")
                    with TabPane("System", id="tab_system"):
                        yield SystemPanel(id="panel_system")
                    with TabPane("About", id="tab_about"):
                        yield AboutPanel(id="panel_about")
                    with TabPane("Log", id="tab_log"):
                        with Vertical(id="log_pane"):
                            yield row("Packet log", Switch(id="log_packets"))
                            yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._attach_panels(None)
        self._open_platform()
        self.set_interval(0.05, self._tick)
        self.action_refresh()

    def on_unmount(self) -> None:
        self._teardown()

    # -- helpers ---------------------------------------------------------

    def log_line(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def _status(self) -> StatusPanel:
        return self.query_one("#status", StatusPanel)

    def status_idle(self, message: str = "") -> None:
        backend = self._platform.backend if self._platform else "n/a"
        self._status().show_idle(backend, message)

    def status_connecting(self, device: DeviceInfo, detail: str) -> None:
        self._status().show_connecting(device, detail)

    def _panels(self) -> list:
        return [
            self.query_one("#panel_playback", PlaybackPanel),
            self.query_one("#panel_sound", SoundPanel),
            self.query_one("#panel_devices", DevicesPanel),
            self.query_one("#panel_system", SystemPanel),
            self.query_one("#panel_about", AboutPanel),
        ]

    def _attach_panels(self, headphones: Headphones | None) -> None:
        for panel in self._panels():
            panel.attach(headphones)

    def _sync_panels(self) -> None:
        for panel in self._panels():
            panel.sync()

    def _open_platform(self) -> None:
        self._teardown(close_platform=True)
        try:
            self._platform = create_connection(ble=self._ble)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self._status().show_idle("n/a", f"[red]Failed to open platform: {exc}[/red]")
            self.log_line(f"[red]platform error:[/red] {exc}")
            return
        self._status().show_idle(self._platform.backend)
        self.log_line(f"Opened platform backend [cyan]{self._platform.backend}[/cyan]")
        self.query_one("#btn_ble", Button).label = f"BLE: {'on' if self._ble else 'off'}"

    def _teardown(self, close_platform: bool = True) -> None:
        if self._headphones is not None:
            self._headphones.close()
            self._headphones = None
        if close_platform and self._platform is not None:
            try:
                self._platform.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._platform.close()
            self._platform = None
        self._connecting = False

    def _on_packet(self, direction: int, frame: bytes) -> None:
        arrow = "[green]<<[/green]" if direction == C.PACKET_DIRECTION_RX else "[blue]>>[/blue]"
        self.call_from_thread(self.log_line, f"{arrow} {frame.hex(' ')}")

    # -- actions ---------------------------------------------------------

    def action_toggle_sidebar(self) -> None:
        self.query_one("#sidebar").toggle_class("-hidden")

    def action_toggle_ble(self) -> None:
        if sys.platform != "win32":
            self.log_line("[yellow]BLE toggle is only available on Windows[/yellow]")
            return
        self._ble = not self._ble
        self._attach_panels(None)
        self._open_platform()
        self.action_refresh()

    def action_refresh(self) -> None:
        self.refresh_devices()

    def action_connect(self) -> None:
        self.connect_selected()

    def action_disconnect(self) -> None:
        if self._platform is None:
            return
        self._teardown(close_platform=False)
        self._attach_panels(None)
        try:
            self._platform.disconnect()
        except Exception as exc:  # noqa: BLE001
            self.log_line(f"[red]disconnect error:[/red] {exc}")
        self._status().show_idle(self._platform.backend, "Disconnected")
        self.log_line("Disconnected")

    def action_cycle_noise(self) -> None:
        headphones = self._headphones
        if headphones is None or not headphones.is_ready():
            self.log_line("[yellow]Headphones not ready[/yellow]")
            return
        try:
            mode = headphones.cycle_noise_mode()
            self.log_line(f"Noise mode → [cyan]{C.NOISE_MODE_NAMES.get(mode, mode)}[/cyan]")
        except result.MDRError as exc:
            self.log_line(f"[red]noise error:[/red] {exc}")

    def action_fetch(self) -> None:
        headphones = self._headphones
        if headphones is None or not headphones.is_ready():
            self.log_line("[yellow]Headphones not ready[/yellow]")
            return
        try:
            headphones.request_sync()
            self.log_line("Fetch requested")
        except result.MDRError as exc:
            self.log_line(f"[red]fetch error:[/red] {exc}")

    # -- events ----------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "btn_refresh": self.action_refresh,
            "btn_connect": self.action_connect,
            "btn_disconnect": self.action_disconnect,
            "btn_ble": self.action_toggle_ble,
        }
        handler = handlers.get(event.button.id or "")
        if handler is not None:
            event.stop()
            handler()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id != "log_packets":
            return
        event.stop()
        self._packet_log = event.value
        headphones = self._headphones
        if headphones is not None:
            headphones.set_packet_callback(self._on_packet if self._packet_log else None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, DeviceListItem):
            self._selected = item.device
            self.log_line(f"Selected [cyan]{item.device.name}[/cyan] ({item.device.address})")

    # -- workers ---------------------------------------------------------

    @work(exclusive=True, thread=True)
    def refresh_devices(self) -> None:
        if self._platform is None:
            self.call_from_thread(self.log_line, "[red]No platform connection[/red]")
            return
        try:
            devices = self._platform.devices()
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self.log_line, f"[red]device list error:[/red] {exc}")
            return

        def apply() -> None:
            view = self.query_one("#devices", ListView)
            view.clear()
            for device in devices:
                view.append(DeviceListItem(device))
            if devices:
                self._selected = devices[0]
                view.index = 0
            self.log_line(f"Found [cyan]{len(devices)}[/cyan] device(s)")

        self.call_from_thread(apply)

    @work(exclusive=True, thread=True)
    def connect_selected(self) -> None:
        if self._platform is None:
            self.call_from_thread(self.log_line, "[red]No platform connection[/red]")
            return
        device = self._selected
        if device is None:
            self.call_from_thread(self.log_line, "[yellow]Select a device first[/yellow]")
            return
        if self._connecting:
            return

        self._connecting = True
        try:
            self.call_from_thread(self.status_connecting, device, "Starting transport…")
            self.call_from_thread(self._attach_panels, None)
            self.call_from_thread(self._teardown, False)

            services = (
                [result.BLE_SERVICE_UUID_TANDEM_OVER_BLE_HPC]
                if self._ble
                else [result.SERVICE_UUID_XM5, result.SERVICE_UUID_LEGACY]
            )
            last_error = ""
            connected = False
            for service in services:
                label = (
                    "BLE"
                    if self._ble
                    else ("V2" if service == result.SERVICE_UUID_XM5 else "V1")
                )
                self.call_from_thread(self.status_connecting, device, f"Trying {label}…")
                self.call_from_thread(self.log_line, f"Connecting via [cyan]{label}[/cyan]…")
                try:
                    self._platform.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    code = self._platform.connect(device.address, service)
                except result.MDRError as exc:
                    last_error = str(exc)
                    continue
                if code not in (result.OK, result.INPROGRESS):
                    last_error = self._platform.last_error() or result.result_string(code)
                    continue

                deadline = time.monotonic() + 12.0
                while time.monotonic() < deadline:
                    poll = self._platform.poll(50)
                    if poll == result.OK:
                        connected = True
                        break
                    if poll not in (result.INPROGRESS, result.ERROR_TIMEOUT):
                        last_error = self._platform.last_error() or result.result_string(poll)
                        break
                if connected:
                    break
                last_error = self._platform.last_error() or last_error or "timeout"

            if not connected:
                self.call_from_thread(
                    self.status_idle, f"[red]Connect failed: {last_error}[/red]"
                )
                self.call_from_thread(self.log_line, f"[red]connect failed:[/red] {last_error}")
                return

            headphones = Headphones(self._platform.connection)
            if self._packet_log:
                headphones.set_packet_callback(self._on_packet)
            headphones.request_init()

            def attached() -> None:
                self._headphones = headphones
                self._attach_panels(headphones)
                self.log_line("[green]Connected — initializing…[/green]")

            self.call_from_thread(attached)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(self.log_line, f"[red]connect error:[/red] {exc}")
            self.call_from_thread(self.status_idle, f"[red]{exc}[/red]")
        finally:
            self._connecting = False

    # -- main loop -------------------------------------------------------

    def _tick(self) -> None:
        headphones = self._headphones
        if headphones is None:
            return
        self._ticks += 1
        changed = False
        try:
            while True:
                event = headphones.poll()
                if event == C.EVENT_NONE:
                    break
                changed = True
                self._last_event = C.EVENT_NAMES.get(event, str(event))
                if event == C.EVENT_INITIALIZE_COMPLETE:
                    self.log_line("[green]Initialize complete[/green]")
                    self._attach_panels(headphones)
                    headphones.request_sync()
                elif event == C.EVENT_ALERT:
                    self.log_line(
                        f"[yellow]alert:[/yellow] {headphones.get_text(C.TEXT_LAST_ALERT)}"
                    )
                elif event == C.EVENT_INTERACTION:
                    self.log_line(
                        f"[cyan]interaction:[/cyan] "
                        f"{headphones.get_text(C.TEXT_LAST_INTERACTION)}"
                    )
                elif event == C.EVENT_DEVICE_MESSAGE:
                    self.log_line(
                        f"[cyan]message:[/cyan] "
                        f"{headphones.get_text(C.TEXT_LAST_DEVICE_MESSAGE)}"
                    )
                elif event != C.EVENT_UNHANDLED:
                    self.log_line(f"Event [magenta]{self._last_event}[/magenta]")

            if headphones.is_ready() and headphones.is_dirty():
                headphones.request_commit()

            if changed or self._ticks % SYNC_INTERVAL == 0:
                self._sync_panels()
            if changed or self._ticks % STATUS_INTERVAL == 0:
                self._status().show_connected(headphones, self._last_event)
        except result.MDRError as exc:
            self.log_line(f"[red]poll error:[/red] {exc}")
            self.action_disconnect()


def main() -> None:
    HeadphonesTui().run()


if __name__ == "__main__":
    main()
