"""Main window: navigation, device bar, worker wiring, default Windows 2000 theme."""

from __future__ import annotations

import sys

from libmdr import constants as C

from .qt_compat import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    Qt,
    QWidget,
)
from .widgets import Switch, available_themes, hbox, set_theme
from .worker import DeviceWorker
from .pages import (
    AboutPage,
    DevicesPage,
    EqualizerPage,
    LogPage,
    OverviewPage,
    PlaybackPage,
    SoundPage,
    SystemPage,
)

_PAGE_TITLES = ["概览", "声音", "均衡器", "播放", "设备", "系统", "关于", "日志"]

_STATUS_COLOR = {
    "idle": "#808080",
    "connecting": "#ffb454",
    "connected": "#54d98c",
    "disconnected": "#808080",
    "failed": "#ff5d5d",
}


class MainWindow(QMainWindow):
    def __init__(self, ble: bool = False) -> None:
        super().__init__()
        self.setWindowTitle("Sony MDR — 桌面控制")
        self.resize(1080, 720)

        self._ble = ble
        self._devices: list[tuple[str, str]] = []
        self._selected: str | None = None
        self._conn_state: str = "idle"

        self._worker = DeviceWorker(ble=ble)

        self._build_ui()
        self._wire_worker()
        self._worker.start()

    # -- controller interface used by pages -------------------------------
    def playback(self, action: str) -> None:
        self._worker.req_playback.emit(action)

    def volume(self, value: int) -> None:
        self._worker.req_volume.emit(value)

    def set(self, name: str, value: int) -> None:
        self._worker.req_set.emit(name, value)

    def set_bool(self, name: str, value: bool) -> None:
        self._worker.req_set_bool.emit(name, value)

    def eq_band(self, index: int, value: int) -> None:
        self._worker.req_eq_band.emit(index, value)

    def paired(self, command: int, address: str) -> None:
        self._worker.req_paired.emit(command, address)

    def general(self, index: int, value: bool) -> None:
        self._worker.req_general.emit(index, value)

    def pairing(self, enabled: bool) -> None:
        self._worker.req_set_bool.emit("pairing", enabled)

    def fetch(self) -> None:
        self._worker.req_fetch.emit()

    # -- UI construction ---------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        self._build_menu()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_device_bar())

        self._tabs = QTabWidget()
        self._pages = [
            OverviewPage(self),
            SoundPage(self),
            EqualizerPage(self),
            PlaybackPage(self),
            DevicesPage(self),
            SystemPage(self),
            AboutPage(self),
            LogPage(self),
        ]
        self._log_page: LogPage = self._pages[-1]
        for title, page in zip(_PAGE_TITLES, self._pages):
            self._tabs.addTab(page, title)
        root.addWidget(self._tabs, 1)

        self.statusBar().showMessage("就绪")

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件(&F)")
        file_menu.addAction("退出(&X)", self.close)
        view_menu = menubar.addMenu("视图(&V)")
        view_menu.addAction(
            "关于本机", lambda: self._tabs.setCurrentWidget(self._pages[6])
        )
        view_menu.addAction(
            "日志", lambda: self._tabs.setCurrentWidget(self._pages[7])
        )
        help_menu = menubar.addMenu("帮助(&H)")
        help_menu.addAction(
            "关于 Sony MDR…", lambda: self._tabs.setCurrentWidget(self._pages[6])
        )

    def _build_device_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("card")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        dev_label = QLabel("设备")
        dev_label.setObjectName("fieldLabel")
        self._device_combo = QComboBox()
        self._device_combo.setMinimumWidth(280)
        self._device_combo.addItem("未发现设备", None)
        self._device_combo.currentIndexChanged.connect(self._on_device_picked)

        self._scan_btn = QPushButton("刷新")
        self._scan_btn.clicked.connect(lambda: self._worker.req_scan.emit())

        left = QWidget()
        left.setLayout(hbox(dev_label, self._device_combo, self._scan_btn))
        layout.addWidget(left, 1)

        self._status_led = QLabel()
        self._status_led.setFixedSize(12, 12)
        self._status_led.setObjectName("statusDot")
        self._set_status_color("#7b8696")
        self._status_text = QLabel("未连接")
        self._status_text.setObjectName("muted")
        layout.addWidget(self._status_led)
        layout.addWidget(self._status_text)

        self._backend_label = QLabel("")
        self._backend_label.setObjectName("muted")
        layout.addWidget(self._backend_label)

        self._ble_switch = Switch("BLE")
        self._ble_switch.setChecked(self._ble)
        self._ble_switch.toggled.connect(self._on_ble_toggle)
        layout.addWidget(self._ble_switch)

        layout.addWidget(QLabel("主题"))
        self._theme_combo = QComboBox()
        for title, key in available_themes():
            self._theme_combo.addItem(title, key)
        idx = self._theme_combo.findData("win2000")
        self._theme_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._theme_combo.currentIndexChanged.connect(self._on_theme)
        layout.addWidget(self._theme_combo)

        self._conn_btn = QPushButton("连接")
        self._conn_btn.setObjectName("primary")
        self._conn_btn.clicked.connect(self._on_conn_btn)
        layout.addWidget(self._conn_btn)

        return bar

    def _set_status_color(self, color: str) -> None:
        # A small square indicator with a 3D edge — no rounded corners.
        self._status_led.setStyleSheet(
            f"background-color: {color}; border: 1px solid #000000;"
        )

    # -- worker wiring -----------------------------------------------------
    def _wire_worker(self) -> None:
        w = self._worker
        w.backend_ready.connect(self._on_backend)
        w.devices_discovered.connect(self._on_devices)
        w.connection_state.connect(self._on_conn_state)
        w.state_updated.connect(self._on_state)
        w.log_message.connect(self._on_log)
        w.event_occurred.connect(self._on_event)

    # -- slots -------------------------------------------------------------

    def _on_backend(self, backend: str) -> None:
        label = {"classic": "经典蓝牙", "ble": "BLE"}.get(backend, backend)
        self._backend_label.setText(f"后端：{label}")

    def _on_devices(self, devices) -> None:  # noqa: ANN001
        self._devices = list(devices)
        prev = self._selected
        self._device_combo.blockSignals(True)
        self._device_combo.clear()
        if self._devices:
            for name, address in self._devices:
                self._device_combo.addItem(f"{name}  ·  {address}", address)
            if prev and any(a == prev for _, a in self._devices):
                self._selected = prev
                self._set_combo_data(prev)
            else:
                self._selected = self._devices[0][1]
                self._device_combo.setCurrentIndex(0)
        else:
            self._device_combo.addItem("未发现设备", None)
            self._selected = None
        self._device_combo.blockSignals(False)
        self._update_conn_btn()

    def _set_combo_data(self, data) -> None:  # noqa: ANN001
        for i in range(self._device_combo.count()):
            if self._device_combo.itemData(i) == data:
                self._device_combo.setCurrentIndex(i)
                return

    def _on_device_picked(self, _index: int) -> None:
        self._selected = self._device_combo.currentData()
        self._update_conn_btn()

    def _on_ble_toggle(self, value: bool) -> None:
        if value == self._ble:
            return
        self._ble = value
        self._worker.req_restart.emit(value)
        self._status_text.setText("切换后端…")
        self._update_conn_btn()

    def _on_theme(self, _index: int) -> None:
        key = self._theme_combo.currentData()
        if key:
            set_theme(QApplication.instance(), key)

    def _on_conn_btn(self) -> None:
        if self._conn_state == "connected":
            self._worker.req_disconnect.emit()
        elif self._selected:
            self._worker.req_connect.emit(self._selected)

    def _on_conn_state(self, state: str) -> None:
        self._conn_state = state
        color = _STATUS_COLOR.get(state, "#7b8696")
        self._set_status_color(color)
        text = {
            "idle": "未连接",
            "connecting": "连接中…",
            "connected": "已连接",
            "disconnected": "已断开",
            "failed": "连接失败",
        }.get(state, state)
        self._status_text.setText(text)
        self.statusBar().showMessage(f"连接状态：{text}")
        self._update_conn_btn()

    def _update_conn_btn(self) -> None:
        if self._conn_state == "connected":
            self._conn_btn.setText("断开")
            self._conn_btn.setEnabled(True)
        elif self._conn_state == "connecting":
            self._conn_btn.setText("连接中…")
            self._conn_btn.setEnabled(False)
        else:
            self._conn_btn.setText("连接")
            self._conn_btn.setEnabled(bool(self._selected))

    def _on_state(self, snap) -> None:  # noqa: ANN001
        for page in self._pages:
            if page is self._log_page:
                continue
            try:
                page.apply(snap)
            except Exception as exc:  # noqa: BLE001
                self._on_log(f"页面更新错误：{exc}")

    def _on_log(self, message: str) -> None:
        self._log_page.append(message)

    def _on_event(self, name: str) -> None:
        self.statusBar().showMessage(f"事件：{name}")

    # -- cleanup -----------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._worker.req_disconnect.emit()
        self._worker.quit()
        self._worker.wait(2000)
        super().closeEvent(event)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Sony MDR 桌面控制（Qt 示例）")
    parser.add_argument(
        "--ble", action="store_true", help="使用 BLE 传输而非经典蓝牙"
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    set_theme(app, "win2000")
    window = MainWindow(ble=args.ble)
    window.show()
    sys.exit(app.exec())
