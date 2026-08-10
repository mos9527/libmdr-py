"""Feature pages for the desktop UI.

Each page receives a ``ctl`` controller (implemented by the main window) and
calls its methods to issue commands.  State is pushed back via ``apply(snap)``.
"""

from __future__ import annotations

from libmdr import constants as C

from .qt_compat import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
    QWidget,
    QHeaderView,
    QPlainTextEdit,
)
from .widgets import (
    BatteryBar,
    Card,
    EnumCombo,
    SectionLabel,
    SegmentedControl,
    SliderRow,
    Switch,
    labeled,
    hbox,
    vbox,
)

# --------------------------------------------------------------------------
# option lists
# --------------------------------------------------------------------------

_NOISE_MODE_OPTS = [
    ("关闭", C.NOISE_MODE_OFF),
    ("降噪", C.NOISE_MODE_CANCELLING),
    ("环境声", C.NOISE_MODE_AMBIENT),
]


def _opts(name_dict, include=None):
    items = [
        (label, value)
        for value, label in name_dict.items()
        if include is None or value in include
    ]
    return sorted(items, key=lambda kv: kv[1])


def _clear_layout(layout) -> None:  # noqa: ANN001
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


# --------------------------------------------------------------------------
# base page
# --------------------------------------------------------------------------


class Page(QWidget):
    def __init__(self, ctl, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctl = ctl

        self._stack = QStackedWidget(self)
        self._placeholder = QLabel("未连接设备。\n请在顶部选择设备并点击「连接」。")
        self._placeholder.setObjectName("hint")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._scroll = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll)
        self._scroll_layout.setSpacing(14)
        self._scroll_layout.setContentsMargins(0, 4, 4, 4)
        self._build_content(self._scroll)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setWidget(self._scroll)

        self._stack.addWidget(self._placeholder)
        self._stack.addWidget(scroller)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._stack)
        self.apply(None)

    def _build_content(self, widget: QWidget) -> None:
        raise NotImplementedError

    def _apply(self, snap: dict) -> None:
        raise NotImplementedError

    def apply(self, snap) -> None:  # noqa: ANN001
        if snap is None:
            self._stack.setCurrentWidget(self._placeholder)
            return
        self._stack.setCurrentWidget(self._stack.widget(1))
        self.blockSignals(True)
        try:
            self._apply(snap)
        finally:
            self.blockSignals(False)


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------


class OverviewPage(Page):
    def _build_content(self, w: QWidget) -> None:
        # identity
        self._ident = Card("设备")
        self._model_name = QLabel("—")
        self._model_name.setObjectName("titleText")
        self._model_sub = QLabel("")
        self._model_sub.setObjectName("muted")
        self._batts = QWidget()
        self._batts_layout = QHBoxLayout(self._batts)
        self._batts_layout.setSpacing(16)
        self._ident.add(self._model_name, self._model_sub, self._batts)

        # noise quick
        self._noise_card = Card("噪声控制")
        self._noise_seg = SegmentedControl(_NOISE_MODE_OPTS)
        self._noise_seg.changed.connect(lambda v: self._ctl.set("noise_mode", v))
        self._ambient = SliderRow("环境声级别", 1, 20, 10)
        self._ambient.valueChanged.connect(lambda v: self._ctl.set("noise_ambient", v))
        self._voice = Switch()
        self._voice.toggled.connect(lambda v: self._ctl.set_bool("noise_voice", v))
        self._noise_card.add(
            self._noise_seg, self._ambient, labeled("聚焦人声", self._voice)
        )

        # playback quick
        self._play_card = Card("播放控制")
        self._prev_btn = QPushButton("上一首")
        self._play_btn = QPushButton("播放 / 暂停")
        self._play_btn.setObjectName("primary")
        self._next_btn = QPushButton("下一首")
        self._prev_btn.clicked.connect(lambda: self._ctl.playback("prev"))
        self._play_btn.clicked.connect(lambda: self._ctl.playback("toggle"))
        self._next_btn.clicked.connect(lambda: self._ctl.playback("next"))
        controls = QWidget()
        controls.setLayout(hbox(self._prev_btn, self._play_btn, self._next_btn))
        self._volume = SliderRow("音量", 0, 30, 0)
        self._volume.valueChanged.connect(lambda v: self._ctl.volume(v))
        self._track_title = QLabel("—")
        self._track_title.setObjectName("bigValue")
        self._track_artist = QLabel("")
        self._track_artist.setObjectName("muted")
        self._play_card.add(controls, self._volume, self._track_title, self._track_artist)

        w.layout().addWidget(self._ident)
        w.layout().addWidget(self._noise_card)
        w.layout().addWidget(self._play_card)
        w.layout().addStretch(1)

    def _apply(self, snap: dict) -> None:
        model = snap.get("model") or {}
        self._model_name.setText(model.get("name", "—"))
        sub = [f"固件 {model['firmware']}" for _ in (0,) if model.get("firmware")]
        if model.get("codec"):
            sub.append(model["codec"])
        if model.get("color"):
            sub.append(model["color"])
        self._model_sub.setText(" · ".join(sub))

        _clear_layout(self._batts_layout)
        for b in snap.get("batteries", []):
            bar = BatteryBar()
            bar.set_level(b["level"], b["charging"] == "charging")
            col = QVBoxLayout()
            col.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.setSpacing(4)
            name = QLabel(b["part"])
            name.setObjectName("muted")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(name)
            col.addWidget(bar)
            self._batts_layout.addLayout(col)
        self._batts_layout.addStretch(1)

        noise = snap.get("noise")
        if noise:
            opts = [("关闭", C.NOISE_MODE_OFF)]
            if noise.get("has_nc"):
                opts.append(("降噪", C.NOISE_MODE_CANCELLING))
            if noise.get("has_ambient"):
                opts.append(("环境声", C.NOISE_MODE_AMBIENT))
            self._noise_seg.set_options(opts)
            self._noise_seg.setValue(noise["mode"])
            ambient_ok = noise.get("has_ambient") and noise["mode"] == C.NOISE_MODE_AMBIENT
            self._ambient.set_enabled(ambient_ok)
            self._ambient.set_value(noise["ambient_level"])
            self._voice.setChecked(noise["focus_on_voice"])
            self._voice.setEnabled(True)
            self._noise_card.setEnabled(True)
        else:
            self._noise_card.setEnabled(False)

        pb = snap.get("playback") or {}
        self._volume.set_value(pb.get("volume", 0))
        self._track_title.setText(pb.get("title") or "未在播放")
        self._track_artist.setText(pb.get("artist") or "")


# --------------------------------------------------------------------------
# Sound (noise details + speak-to-chat + listening)
# --------------------------------------------------------------------------


class SoundPage(Page):
    def _build_content(self, w: QWidget) -> None:
        # noise details
        self._noise_card = Card("噪声控制")
        self._noise_seg = SegmentedControl(_NOISE_MODE_OPTS)
        self._noise_seg.changed.connect(lambda v: self._ctl.set("noise_mode", v))
        self._ambient = SliderRow("环境声级别", 1, 20, 10)
        self._ambient.valueChanged.connect(lambda v: self._ctl.set("noise_ambient", v))
        self._voice = Switch()
        self._voice.toggled.connect(lambda v: self._ctl.set_bool("noise_voice", v))
        self._adaptive = Switch()
        self._adaptive.toggled.connect(lambda v: self._ctl.set_bool("noise_adaptive", v))
        self._adaptive_sens = EnumCombo(
            "自适应灵敏度", _opts(C.ADAPTIVE_SENSITIVITY_NAMES)
        )
        self._adaptive_sens.valueChanged.connect(
            lambda v: self._ctl.set("noise_sensitivity", v)
        )
        self._button = EnumCombo("按键行为", _opts(C.NOISE_BUTTON_NAMES))
        self._button.valueChanged.connect(lambda v: self._ctl.set("noise_button", v))
        self._noise_card.add(
            self._noise_seg,
            self._ambient,
            labeled("聚焦人声", self._voice),
            labeled("自适应环境声", self._adaptive),
            self._adaptive_sens,
            self._button,
        )

        # speak-to-chat
        self._stc_card = Card("语音聊天 (Speak-to-Chat)")
        self._stc_en = Switch()
        self._stc_en.toggled.connect(lambda v: self._ctl.set_bool("stc_enabled", v))
        self._stc_sens = EnumCombo("灵敏度", _opts(C.SPEECH_SENSITIVITY_NAMES))
        self._stc_sens.valueChanged.connect(lambda v: self._ctl.set("stc_sensitivity", v))
        self._stc_timeout = EnumCombo("超时", _opts(C.SPEAK_TIMEOUT_NAMES))
        self._stc_timeout.valueChanged.connect(lambda v: self._ctl.set("stc_timeout", v))
        self._stc_card.add(
            labeled("启用", self._stc_en), self._stc_sens, self._stc_timeout
        )

        # listening
        self._listen_card = Card("聆听模式")
        self._listen_mode = EnumCombo("模式", _opts(C.LISTENING_MODE_NAMES))
        self._listen_mode.valueChanged.connect(lambda v: self._ctl.set("listening_mode", v))
        self._listen_room = EnumCombo("房间大小", _opts(C.ROOM_SIZE_NAMES))
        self._listen_room.valueChanged.connect(lambda v: self._ctl.set("listening_room", v))
        self._listen_card.add(self._listen_mode, self._listen_room)

        w.layout().addWidget(self._noise_card)
        w.layout().addWidget(self._stc_card)
        w.layout().addWidget(self._listen_card)
        w.layout().addStretch(1)

    def _apply(self, snap: dict) -> None:
        noise = snap.get("noise")
        if noise:
            opts = [("关闭", C.NOISE_MODE_OFF)]
            if noise.get("has_nc"):
                opts.append(("降噪", C.NOISE_MODE_CANCELLING))
            if noise.get("has_ambient"):
                opts.append(("环境声", C.NOISE_MODE_AMBIENT))
            self._noise_seg.set_options(opts)
            self._noise_seg.setValue(noise["mode"])
            ambient_ok = noise.get("has_ambient") and noise["mode"] == C.NOISE_MODE_AMBIENT
            self._ambient.set_enabled(ambient_ok)
            self._ambient.set_value(noise["ambient_level"])
            self._voice.setChecked(noise["focus_on_voice"])
            self._voice.setEnabled(True)
            self._adaptive.setChecked(noise["adaptive_ambient"])
            self._adaptive.setEnabled(noise.get("has_adaptive", False))
            self._adaptive_sens.set_value(noise["adaptive_sensitivity"])
            self._adaptive_sens.set_enabled(noise.get("has_adaptive", False))
            self._button.set_value(noise["button_mode"])
            self._button.set_enabled(noise.get("has_button", False))
            self._noise_card.setEnabled(True)
        else:
            self._noise_card.setEnabled(False)

        speak = snap.get("speak")
        if speak:
            self._stc_en.setChecked(speak["enabled"])
            self._stc_sens.set_value(speak["sensitivity"])
            self._stc_timeout.set_value(speak["timeout"])
            self._stc_card.setEnabled(True)
        else:
            self._stc_card.setEnabled(False)

        listening = snap.get("listening")
        if listening:
            self._listen_mode.set_value(listening["mode"])
            self._listen_room.set_value(listening["room"])
            self._listen_card.setEnabled(True)
        else:
            self._listen_card.setEnabled(False)


# --------------------------------------------------------------------------
# Equalizer
# --------------------------------------------------------------------------


class EqualizerPage(Page):
    def _build_content(self, w: QWidget) -> None:
        self._eq_card = Card("均衡器")
        self._preset = EnumCombo("预设", _opts(C.EQUALIZER_PRESET_NAMES))
        self._preset.valueChanged.connect(lambda v: self._ctl.set("eq_preset", v))
        self._bass = SliderRow("清低音 (Clear Bass)", -10, 10, 0)
        self._bass.valueChanged.connect(lambda v: self._ctl.set("eq_bass", v))
        self._dsee = Switch()
        self._dsee.toggled.connect(lambda v: self._ctl.set_bool("eq_dsee", v))
        self._dsee_label = QLabel("")
        self._dsee_label.setObjectName("muted")
        self._bands_widget = QWidget()
        self._bands_layout = QVBoxLayout(self._bands_widget)
        self._bands_layout.setContentsMargins(0, 0, 0, 0)
        self._bands_layout.setSpacing(6)
        self._eq_card.add(
            self._preset,
            self._bass,
            labeled("DSEE", self._dsee),
            self._dsee_label,
            SectionLabel("频段增益"),
            self._bands_widget,
        )
        w.layout().addWidget(self._eq_card)
        w.layout().addStretch(1)
        self._band_sliders = []
        self._band_count = None

    def _rebuild_bands(self, band_count: int, labels, lo: int, hi: int) -> None:
        self._band_count = band_count
        _clear_layout(self._bands_layout)
        self._band_sliders = []
        for i in range(band_count):
            row = SliderRow(labels[i] if i < len(labels) else f"#{i}", lo, hi, 0)
            row.valueChanged.connect(
                lambda v, idx=i: self._ctl.eq_band(idx, v)
            )
            self._bands_layout.addWidget(row)
            self._band_sliders.append(row)

    def _apply(self, snap: dict) -> None:
        eq = snap.get("equalizer")
        if not eq:
            self._eq_card.setEnabled(False)
            return
        self._eq_card.setEnabled(True)
        band_count = eq["band_count"] or 5
        labels = C.EQUALIZER_BAND_LABELS.get(band_count, tuple(f"#{i}" for i in range(band_count)))
        lo, hi = C.EQUALIZER_BAND_RANGE.get(band_count, (-10, 10))
        if self._band_count != band_count:
            self._rebuild_bands(band_count, labels, lo, hi)
        self._preset.set_value(eq["preset"])
        self._bass.set_value(eq["clear_bass"])
        for row, value in zip(self._band_sliders, eq["bands"]):
            row.set_value(value)
        self._dsee.setChecked(eq["dsee_enabled"])
        self._dsee.setEnabled(eq.get("has_dsee", False))
        self._dsee_label.setText(
            C.DSEE_TYPE_NAMES.get(eq["dsee_type"], "DSEE") if eq["dsee_enabled"] else ""
        )


# --------------------------------------------------------------------------
# Playback (full transport)
# --------------------------------------------------------------------------


class PlaybackPage(Page):
    def _build_content(self, w: QWidget) -> None:
        self._card = Card("播放")
        self._title = QLabel("—")
        self._title.setObjectName("titleText")
        self._artist = QLabel("")
        self._artist.setObjectName("muted")
        self._album = QLabel("")
        self._album.setObjectName("muted")
        self._prev = QPushButton("上一首")
        self._play = QPushButton("播放 / 暂停")
        self._play.setObjectName("primary")
        self._next = QPushButton("下一首")
        self._prev.clicked.connect(lambda: self._ctl.playback("prev"))
        self._play.clicked.connect(lambda: self._ctl.playback("toggle"))
        self._next.clicked.connect(lambda: self._ctl.playback("next"))
        controls = QWidget()
        controls.setLayout(hbox(self._prev, self._play, self._next))
        self._volume = SliderRow("音量", 0, 30, 0)
        self._volume.valueChanged.connect(lambda v: self._ctl.volume(v))
        self._card.add(self._title, self._artist, self._album, controls, self._volume)
        w.layout().addWidget(self._card)
        w.layout().addStretch(1)

    def _apply(self, snap: dict) -> None:
        pb = snap.get("playback") or {}
        self._title.setText(pb.get("title") or "未在播放")
        self._artist.setText(pb.get("artist") or "")
        self._album.setText(pb.get("album") or "")
        self._volume.set_value(pb.get("volume", 0))


# --------------------------------------------------------------------------
# Devices (pairing)
# --------------------------------------------------------------------------


class DevicesPage(Page):
    def _build_content(self, w: QWidget) -> None:
        self._pair_card = Card("配对模式")
        self._pair_en = Switch()
        self._pair_en.toggled.connect(lambda v: self._ctl.pairing(v))
        self._pair_hint = QLabel("开启后可被新设备发现并完成配对。")
        self._pair_hint.setObjectName("muted")
        self._pair_card.add(labeled("可被发现", self._pair_en), self._pair_hint)

        self._dev_card = Card("已配对设备")
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["名称", "地址", "已连接", "播放中"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._connect_btn = QPushButton("连接")
        self._connect_btn.setObjectName("primary")
        self._disconnect_btn = QPushButton("断开")
        self._playback_btn = QPushButton("设为播放")
        self._unpair_btn = QPushButton("取消配对")
        self._unpair_btn.setObjectName("danger")
        self._connect_btn.clicked.connect(lambda: self._act(C.PAIRED_DEVICE_CONNECT))
        self._disconnect_btn.clicked.connect(lambda: self._act(C.PAIRED_DEVICE_DISCONNECT))
        self._playback_btn.clicked.connect(lambda: self._act(C.PAIRED_DEVICE_SELECT_PLAYBACK))
        self._unpair_btn.clicked.connect(lambda: self._act(C.PAIRED_DEVICE_UNPAIR))
        bar = QWidget()
        bar.setLayout(
            hbox(
                self._connect_btn,
                self._disconnect_btn,
                self._playback_btn,
                self._unpair_btn,
            )
        )
        self._dev_card.add(self._table, bar)
        w.layout().addWidget(self._pair_card)
        w.layout().addWidget(self._dev_card)
        w.layout().addStretch(1)

    def _selected_address(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        return self._table.item(row, 1).text()

    def _act(self, command: int) -> None:
        addr = self._selected_address()
        if addr:
            self._ctl.paired(command, addr)

    def _apply(self, snap: dict) -> None:
        pairing = snap.get("pairing")
        if pairing:
            self._pair_en.setChecked(pairing["enabled"])
        devices = snap.get("paired_devices") or []
        self._table.setRowCount(len(devices))
        for i, d in enumerate(devices):
            self._table.setItem(i, 0, QTableWidgetItem(d["name"]))
            self._table.setItem(i, 1, QTableWidgetItem(d["address"]))
            self._table.setItem(i, 2, QTableWidgetItem("是" if d["connected"] else "—"))
            self._table.setItem(i, 3, QTableWidgetItem("是" if d["playback"] else "—"))


# --------------------------------------------------------------------------
# System (power / voice / assignable / connection / safe / general)
# --------------------------------------------------------------------------


class SystemPage(Page):
    def _build_content(self, w: QWidget) -> None:
        # power
        self._power_card = Card("电源与佩戴")
        self._apo = EnumCombo("自动关机", _opts(C.AUTO_POWER_OFF_NAMES))
        self._apo.valueChanged.connect(lambda v: self._ctl.set("power_apo", v))
        self._wearing = EnumCombo(
            "佩戴检测",
            [
                ("不可用", C.WEARING_POWER_UNAVAILABLE),
                ("禁用", C.WEARING_POWER_DISABLED),
                ("摘下时关机", C.WEARING_POWER_WHEN_REMOVED),
            ],
        )
        self._wearing.valueChanged.connect(lambda v: self._ctl.set("power_wearing", v))
        self._autopause = Switch()
        self._autopause.toggled.connect(lambda v: self._ctl.set_bool("power_autopause", v))
        self._gesture = Switch()
        self._gesture.toggled.connect(lambda v: self._ctl.set_bool("power_gesture", v))
        self._shutdown_btn = QPushButton("关闭耳机")
        self._shutdown_btn.setObjectName("danger")
        self._shutdown_btn.clicked.connect(lambda: self._ctl.set("power_shutdown", 1))
        self._power_card.add(
            self._apo,
            self._wearing,
            labeled("摘下自动暂停", self._autopause),
            labeled("头部手势", self._gesture),
            self._shutdown_btn,
        )

        # voice guidance
        self._vg_card = Card("语音引导")
        self._vg_en = Switch()
        self._vg_en.toggled.connect(lambda v: self._ctl.set_bool("voice_enabled", v))
        self._vg_vol = SliderRow("音量", -6, 6, 0)
        self._vg_vol.valueChanged.connect(lambda v: self._ctl.set("voice_volume", v))
        self._vg_card.add(labeled("启用", self._vg_en), self._vg_vol)

        # assignable
        self._assign_card = Card("触控自定义")
        assign_opts = _opts(C.ASSIGNABLE_ACTION_NAMES, include=range(7))
        self._assign_left = EnumCombo("左耳", assign_opts)
        self._assign_left.valueChanged.connect(lambda v: self._ctl.set("assign_left", v))
        self._assign_right = EnumCombo("右耳", assign_opts)
        self._assign_right.valueChanged.connect(lambda v: self._ctl.set("assign_right", v))
        self._assign_card.add(self._assign_left, self._assign_right)

        # connection
        self._conn_card = Card("连接模式")
        self._conn = EnumCombo(
            "优先级",
            [
                ("音质优先", C.AUDIO_PRIORITY_QUALITY),
                ("稳定优先", C.AUDIO_PRIORITY_STABILITY),
            ],
        )
        self._conn.valueChanged.connect(lambda v: self._ctl.set("conn_priority", v))
        self._conn_card.add(self._conn)

        # safe listening
        self._safe_card = Card("安全聆听")
        self._safe_prev = Switch()
        self._safe_prev.toggled.connect(lambda v: self._ctl.set_bool("safe_preview", v))
        self._safe_label = QLabel("")
        self._safe_label.setObjectName("muted")
        self._safe_card.add(labeled("试听提示", self._safe_prev), self._safe_label)

        # general settings (dynamic)
        self._gen_card = Card("通用设置")
        self._gen_layout = QVBoxLayout()
        self._gen_layout.setContentsMargins(0, 0, 0, 0)
        self._gen_layout.setSpacing(8)
        self._gen_card.add(self._gen_layout)
        self._gen_switches = {}

        w.layout().addWidget(self._power_card)
        w.layout().addWidget(self._vg_card)
        w.layout().addWidget(self._assign_card)
        w.layout().addWidget(self._conn_card)
        w.layout().addWidget(self._safe_card)
        w.layout().addWidget(self._gen_card)
        w.layout().addStretch(1)

    def _rebuild_general(self, settings) -> None:
        _clear_layout(self._gen_layout)
        self._gen_switches = {}
        for s in settings:
            if s["type"] != C.GENERAL_SETTING_BOOLEAN or not s["writable"]:
                continue
            sw = Switch()
            sw.setEnabled(s["writable"])
            sw.setChecked(s["value"])
            sw.toggled.connect(
                lambda v, idx=s["index"]: self._ctl.general(idx, v)
            )
            label = s["subject"] or f"设置 #{s['index']}"
            row = labeled(label, sw)
            self._gen_layout.addWidget(row)
            self._gen_switches[s["index"]] = sw
        if self._gen_layout.count() == 0:
            hint = QLabel("此设备没有可调的通用设置。")
            hint.setObjectName("muted")
            self._gen_layout.addWidget(hint)

    def _apply(self, snap: dict) -> None:
        power = snap.get("power")
        if power:
            self._power_card.setEnabled(True)
            if power.get("has_apo"):
                self._apo.set_enabled(True)
                self._apo.set_value(power["auto_power_off_minutes"])
            else:
                self._apo.set_enabled(False)
            if power.get("has_wearing"):
                self._wearing.set_enabled(True)
                self._wearing.set_value(power["wearing_power"])
            else:
                self._wearing.set_enabled(False)
            if power.get("has_autopause"):
                self._autopause.setEnabled(True)
                self._autopause.setChecked(power["auto_pause"])
            else:
                self._autopause.setEnabled(False)
            if power.get("has_gesture"):
                self._gesture.setEnabled(True)
                self._gesture.setChecked(power["head_gesture"])
            else:
                self._gesture.setEnabled(False)
            self._shutdown_btn.setEnabled(power.get("has_shutdown", False))
        else:
            self._power_card.setEnabled(False)

        voice = snap.get("voice")
        if voice:
            self._vg_card.setEnabled(True)
            self._vg_en.setChecked(voice["enabled"])
            self._vg_vol.set_value(voice["volume"])
        else:
            self._vg_card.setEnabled(False)

        assign = snap.get("assignable")
        if assign:
            self._assign_card.setEnabled(True)
            self._assign_left.set_value(assign["left"])
            self._assign_right.set_value(assign["right"])
        else:
            self._assign_card.setEnabled(False)

        conn = snap.get("connection_mode")
        if conn:
            self._conn_card.setEnabled(True)
            self._conn.set_value(conn["audio_priority"])
        else:
            self._conn_card.setEnabled(False)

        safe = snap.get("safe_listening")
        if safe:
            self._safe_card.setEnabled(True)
            self._safe_prev.setChecked(safe["preview"])
            self._safe_label.setText(f"当前声压：{safe['sound_pressure']}")
        else:
            self._safe_card.setEnabled(False)

        gen = snap.get("general_settings") or []
        signature = {s["index"]: (s["value"], s["writable"]) for s in gen}
        if signature != getattr(self, "_gen_signature", None):
            self._gen_signature = signature
            self._rebuild_general(gen)
        else:
            for s in gen:
                sw = self._gen_switches.get(s["index"])
                if sw is not None:
                    sw.setChecked(s["value"])


# --------------------------------------------------------------------------
# About (identity / capabilities / messages)
# --------------------------------------------------------------------------


class AboutPage(Page):
    def _build_content(self, w: QWidget) -> None:
        self._info_card = Card("设备信息")
        self._info_layout = QVBoxLayout()
        self._info_layout.setContentsMargins(0, 0, 0, 0)
        self._info_layout.setSpacing(4)
        self._info_card.add(self._info_layout)

        self._cap_card = Card("能力")
        self._cap_table = QTableWidget(0, 2)
        self._cap_table.setHorizontalHeaderLabels(["功能", "可用性"])
        self._cap_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._cap_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._cap_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._cap_card.add(self._cap_table)

        self._msg_card = Card("设备消息")
        self._msg_layout = QVBoxLayout()
        self._msg_layout.setContentsMargins(0, 0, 0, 0)
        self._msg_layout.setSpacing(4)
        self._msg_card.add(self._msg_layout)

        self._fetch_btn = QPushButton("刷新状态")
        self._fetch_btn.setObjectName("primary")
        self._fetch_btn.clicked.connect(lambda: self._ctl.fetch())

        w.layout().addWidget(self._info_card)
        w.layout().addWidget(self._cap_card)
        w.layout().addWidget(self._msg_card)
        w.layout().addWidget(self._fetch_btn)
        w.layout().addStretch(1)

    def _apply(self, snap: dict) -> None:
        model = snap.get("model") or {}
        rows = [
            ("型号", model.get("name", "—")),
            ("系列", model.get("series", "")),
            ("颜色", model.get("color", "")),
            ("固件", model.get("firmware", "")),
            ("编解码", model.get("codec", "")),
            ("协议版本", str(model.get("protocol", ""))),
            ("唯一 ID", model.get("unique_id", "")),
        ]
        _clear_layout(self._info_layout)
        for k, v in rows:
            if not v:
                continue
            r = QLabel(f"<b>{k}</b>：{v}")
            self._info_layout.addWidget(r)

        features = snap.get("features") or {}
        self._cap_table.setRowCount(len(features))
        for i, (fid, name) in enumerate(C.FEATURE_NAMES.items()):
            avail = features.get(fid, "unknown")
            self._cap_table.setItem(i, 0, QTableWidgetItem(name))
            self._cap_table.setItem(i, 1, QTableWidgetItem(avail))

        messages = snap.get("messages") or {}
        _clear_layout(self._msg_layout)
        for label, key in (
            ("最后错误", "last_error"),
            ("提醒", "last_alert"),
            ("交互", "last_interaction"),
            ("设备消息", "last_device_message"),
        ):
            text = messages.get(key, "")
            r = QLabel(f"<b>{label}</b>：{text or '—'}")
            r.setWordWrap(True)
            self._msg_layout.addWidget(r)


# --------------------------------------------------------------------------
# Log
# --------------------------------------------------------------------------


class LogPage(Page):
    def _build_content(self, w: QWidget) -> None:
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        w.layout().addWidget(self._log)

    def append(self, text: str) -> None:
        self._log.appendPlainText(text)

    def _apply(self, snap: dict) -> None:
        pass
