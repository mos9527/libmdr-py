"""Small Textual TUI for libmdr / libmdr-bt.

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
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, RichLog, Static

from libmdr import Headphones, constants, result
from libmdr.connection import DeviceInfo
from libmdr_bt import PlatformConnection, create_connection


def _battery_line(batteries) -> str:
    if not batteries:
        return "Batteries: (none)"
    parts = []
    for battery in batteries:
        if not battery.present:
            continue
        name = constants.BATTERY_PART_NAMES.get(int(battery.part), f"part{battery.part}")
        charging = {
            constants.CHARGING_YES: "+",
            constants.CHARGING_COMPLETE: "=",
        }.get(int(battery.charging), "")
        parts.append(f"{name} {battery.level_percent}%{charging}")
    return "Batteries: " + (", ".join(parts) if parts else "(none present)")


class DeviceListItem(ListItem):
    def __init__(self, device: DeviceInfo) -> None:
        super().__init__(Label(f"{device.name}  [{device.address}]"))
        self.device = device


class StatusPanel(Static):
    def show_idle(self, backend: str, message: str = "") -> None:
        self.update(
            f"[b]Backend[/b] {backend}\n"
            f"[b]State[/b] disconnected\n"
            f"{message}"
        )

    def show_connecting(self, device: DeviceInfo, detail: str) -> None:
        self.update(
            f"[b]Device[/b] {device.name}\n"
            f"[b]Address[/b] {device.address}\n"
            f"[b]State[/b] connecting…\n"
            f"{detail}"
        )

    def show_connected(self, headphones: Headphones, last_event: str) -> None:
        model = headphones.get_text(constants.TEXT_MODEL_NAME) or "(unknown model)"
        fw = headphones.get_text(constants.TEXT_FIRMWARE_VERSION)
        noise_name = "n/a"
        ambient = ""
        try:
            if headphones.feature_available(constants.FEATURE_NOISE_CANCELLING) or headphones.feature_available(
                constants.FEATURE_AMBIENT_SOUND
            ):
                noise = headphones.get_noise_control()
                noise_name = constants.NOISE_MODE_NAMES.get(int(noise.mode), str(noise.mode))
                ambient = f"  ambient={noise.ambient_level}"
        except result.MDRError:
            pass

        ready = "yes" if headphones.is_ready() else "no"
        dirty = "yes" if headphones.is_dirty() else "no"
        initialized = "yes" if headphones.is_initialized() else "no"
        batteries = []
        try:
            batteries = headphones.get_batteries()
        except result.MDRError:
            pass

        self.update(
            f"[b]Model[/b] {model}\n"
            f"[b]Firmware[/b] {fw or 'n/a'}\n"
            f"[b]Init/Ready/Dirty[/b] {initialized}/{ready}/{dirty}\n"
            f"[b]Noise[/b] {noise_name}{ambient}\n"
            f"{_battery_line(batteries)}\n"
            f"[b]Last event[/b] {last_event}"
        )


class HeadphonesTui(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }
    #body {
        height: 1fr;
    }
    #sidebar {
        width: 42%;
        border: solid $accent;
    }
    #main {
        width: 1fr;
        border: solid $primary;
    }
    #status {
        height: auto;
        min-height: 8;
        padding: 1;
    }
    #log {
        height: 1fr;
    }
    #toolbar {
        height: auto;
        dock: bottom;
        padding: 0 1;
    }
    """

    TITLE = "libmdr TUI"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh devices"),
        Binding("c", "connect", "Connect"),
        Binding("d", "disconnect", "Disconnect"),
        Binding("n", "cycle_noise", "Cycle ANC"),
        Binding("f", "fetch", "Fetch"),
        Binding("b", "toggle_ble", "Toggle BLE"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._ble = False
        self._platform: PlatformConnection | None = None
        self._headphones: Headphones | None = None
        self._selected: DeviceInfo | None = None
        self._last_event = "none"
        self._connecting = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("Paired devices", id="devices_title")
                yield ListView(id="devices")
                with Horizontal(id="toolbar"):
                    yield Button("Refresh", id="btn_refresh")
                    yield Button("Connect", id="btn_connect", variant="primary")
                    yield Button("BLE: off", id="btn_ble")
            with Vertical(id="main"):
                yield StatusPanel(id="status")
                yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._open_platform()
        self.set_interval(0.05, self._tick)
        self.action_refresh()

    def on_unmount(self) -> None:
        self._teardown()

    def _log(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def _status(self) -> StatusPanel:
        return self.query_one("#status", StatusPanel)

    def _devices_view(self) -> ListView:
        return self.query_one("#devices", ListView)

    def _ble_button(self) -> Button:
        return self.query_one("#btn_ble", Button)

    def _open_platform(self) -> None:
        self._teardown(close_platform=True)
        try:
            self._platform = create_connection(ble=self._ble)
        except Exception as exc:
            self._status().show_idle("n/a", f"[red]Failed to open platform: {exc}[/red]")
            self._log(f"[red]platform error:[/red] {exc}")
            return
        self._status().show_idle(self._platform.backend)
        self._log(f"Opened platform backend [cyan]{self._platform.backend}[/cyan]")
        self._ble_button().label = f"BLE: {'on' if self._ble else 'off'}"

    def _teardown(self, close_platform: bool = True) -> None:
        if self._headphones is not None:
            self._headphones.close()
            self._headphones = None
        if close_platform and self._platform is not None:
            try:
                self._platform.disconnect()
            except Exception:
                pass
            self._platform.close()
            self._platform = None
        self._connecting = False

    def action_toggle_ble(self) -> None:
        if sys.platform != "win32":
            self._log("[yellow]BLE toggle is only available on Windows[/yellow]")
            return
        self._ble = not self._ble
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
        try:
            self._platform.disconnect()
        except Exception as exc:
            self._log(f"[red]disconnect error:[/red] {exc}")
        self._status().show_idle(self._platform.backend, "Disconnected")
        self._log("Disconnected")

    def action_cycle_noise(self) -> None:
        if self._headphones is None or not self._headphones.is_ready():
            self._log("[yellow]Headphones not ready[/yellow]")
            return
        try:
            mode = self._headphones.cycle_noise_mode()
            self._log(
                "Noise mode -> "
                f"[cyan]{constants.NOISE_MODE_NAMES.get(mode, mode)}[/cyan]"
            )
        except result.MDRError as exc:
            self._log(f"[red]noise error:[/red] {exc}")

    def action_fetch(self) -> None:
        if self._headphones is None or not self._headphones.is_ready():
            self._log("[yellow]Headphones not ready[/yellow]")
            return
        try:
            self._headphones.request_fetch()
            self._log("Fetch requested")
        except result.MDRError as exc:
            self._log(f"[red]fetch error:[/red] {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_refresh":
            self.action_refresh()
        elif event.button.id == "btn_connect":
            self.action_connect()
        elif event.button.id == "btn_ble":
            self.action_toggle_ble()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, DeviceListItem):
            self._selected = item.device
            self._log(f"Selected [cyan]{item.device.name}[/cyan] ({item.device.address})")

    @work(exclusive=True, thread=True)
    def refresh_devices(self) -> None:
        if self._platform is None:
            self.call_from_thread(self._log, "[red]No platform connection[/red]")
            return
        try:
            devices = self._platform.devices()
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]device list error:[/red] {exc}")
            return

        def apply() -> None:
            view = self._devices_view()
            view.clear()
            for device in devices:
                view.append(DeviceListItem(device))
            if devices:
                self._selected = devices[0]
                view.index = 0
            self._log(f"Found [cyan]{len(devices)}[/cyan] device(s)")

        self.call_from_thread(apply)

    @work(exclusive=True, thread=True)
    def connect_selected(self) -> None:
        if self._platform is None:
            self.call_from_thread(self._log, "[red]No platform connection[/red]")
            return
        device = self._selected
        if device is None:
            self.call_from_thread(self._log, "[yellow]Select a device first[/yellow]")
            return
        if self._connecting:
            return

        self._connecting = True
        try:
            self.call_from_thread(
                self._status().show_connecting, device, "Starting transport…"
            )
            self.call_from_thread(self._teardown, False)

            services = (
                [result.BLE_SERVICE_UUID_TANDEM_OVER_BLE_HPC]
                if self._ble
                else [result.SERVICE_UUID_XM5, result.SERVICE_UUID_LEGACY]
            )
            last_error = ""
            connected = False
            for service in services:
                label = "BLE" if self._ble else (
                    "V2" if service == result.SERVICE_UUID_XM5 else "V1"
                )
                self.call_from_thread(
                    self._status().show_connecting, device, f"Trying {label}…"
                )
                self.call_from_thread(self._log, f"Connecting via [cyan]{label}[/cyan]…")
                try:
                    self._platform.disconnect()
                except Exception:
                    pass
                try:
                    code = self._platform.connect(device.address, service)
                except result.MDRError as exc:
                    last_error = str(exc)
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
                    self._status().show_idle,
                    self._platform.backend,
                    f"[red]Connect failed: {last_error}[/red]",
                )
                self.call_from_thread(self._log, f"[red]connect failed:[/red] {last_error}")
                return

            headphones = Headphones(self._platform.connection)
            headphones.request_init()

            def attached() -> None:
                self._headphones = headphones
                self._log("[green]Connected — initializing…[/green]")

            self.call_from_thread(attached)
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]connect error:[/red] {exc}")
            backend = self._platform.backend if self._platform else "n/a"
            self.call_from_thread(
                self._status().show_idle,
                backend,
                f"[red]{exc}[/red]",
            )
        finally:
            self._connecting = False

    def _tick(self) -> None:
        if self._headphones is None:
            return
        try:
            while True:
                event = self._headphones.poll()
                if event == constants.EVENT_NONE:
                    break
                self._last_event = constants.EVENT_NAMES.get(event, str(event))
                if event == constants.EVENT_INITIALIZE_COMPLETE:
                    self._log("[green]Initialize complete[/green]")
                elif event not in (constants.EVENT_UNHANDLED,):
                    self._log(f"Event [magenta]{self._last_event}[/magenta]")

            if self._headphones.is_ready() and self._headphones.is_dirty():
                self._headphones.request_commit()

            self._status().show_connected(self._headphones, self._last_event)
        except result.MDRError as exc:
            self._log(f"[red]poll error:[/red] {exc}")
            self.action_disconnect()


def main() -> None:
    HeadphonesTui().run()


if __name__ == "__main__":
    main()
