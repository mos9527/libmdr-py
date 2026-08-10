"""Reusable desktop-first widgets and the dark theme stylesheet."""

from __future__ import annotations

from .qt_compat import (
    QApplication,
    QBrush,
    QColor,
    QFont,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPainter,
    QPen,
    QPushButton,
    QProgressBar,
    QSlider,
    QSizePolicy,
    QButtonGroup,
    QComboBox,
    QStyleFactory,
    QVBoxLayout,
    Qt,
    Signal,
    QWidget,
    QPointF,
)

# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------

# Theme choices offered in the UI. ``key`` selects the Qt style; themes that
# are not available on the current platform fall back automatically.
THEMES = [
    ("现代 Windows", "windowsvista"),
    ("经典 Windows", "windows"),
    ("深色 Fusion", "fusion"),
]


def available_themes() -> list:
    """Return only the themes whose underlying Qt style exists here."""
    keys = {k.lower() for k in QStyleFactory.keys()}
    return [t for t in THEMES if t[1] in keys or t[1] == "fusion"]


def _style_for(key: str) -> str:
    keys = [k.lower() for k in QStyleFactory.keys()]
    if key in keys:
        idx = keys.index(key)
        return QStyleFactory.keys()[idx]
    if "fusion" in keys:
        return QStyleFactory.keys()[keys.index("fusion")]
    return QStyleFactory.keys()[0] if keys else ""


def set_theme(app: QApplication, key: str) -> None:
    """Apply a theme by its ``key`` (see ``THEMES``)."""
    style_name = _style_for(key)
    if style_name:
        app.setStyle(style_name)

    if key == "fusion":
        _apply_dark_palette(app)
        app.setStyleSheet(STYLE_DARK)
    else:
        # Native styles: use the OS palette and a light structural sheet so the
        # interactive controls keep their native look.
        app.setPalette(app.style().standardPalette())
        app.setStyleSheet(STYLE_NATIVE)


def _apply_dark_palette(app: QApplication) -> None:
    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, QColor("#0e1116"))
    palette.setColor(palette.ColorRole.WindowText, QColor("#e7ebf2"))
    palette.setColor(palette.ColorRole.Base, QColor("#161b22"))
    palette.setColor(palette.ColorRole.AlternateBase, QColor("#1c232d"))
    palette.setColor(palette.ColorRole.ToolTipBase, QColor("#161b22"))
    palette.setColor(palette.ColorRole.ToolTipText, QColor("#e7ebf2"))
    palette.setColor(palette.ColorRole.Text, QColor("#e7ebf2"))
    palette.setColor(palette.ColorRole.Button, QColor("#222b38"))
    palette.setColor(palette.ColorRole.ButtonText, QColor("#e7ebf2"))
    palette.setColor(palette.ColorRole.BrightText, QColor("#7ee0ff"))
    palette.setColor(palette.ColorRole.Highlight, QColor("#3b82f6"))
    palette.setColor(palette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(palette.ColorRole.Link, QColor("#5cc8ff"))
    palette.setColor(palette.ColorRole.Light, QColor("#2a3340"))
    palette.setColor(palette.ColorRole.Midlight, QColor("#2a3340"))
    palette.setColor(palette.ColorRole.Mid, QColor("#11161d"))
    palette.setColor(palette.ColorRole.Dark, QColor("#0a0d12"))
    palette.setColor(palette.ColorRole.Shadow, QColor("#000000"))
    app.setPalette(palette)


def apply_theme(app: QApplication) -> None:
    """Backwards-compatible default: the dark Fusion theme."""
    set_theme(app, "fusion")


# Dark custom theme -------------------------------------------------------
STYLE_DARK = """
QWidget {
    font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
    font-size: 13px;
}
QMainWindow, QWidget#central {
    background: #0e1116;
}

/* Navigation sidebar */
QListWidget#nav {
    background: #11161d;
    border: none;
    border-right: 1px solid #1d242e;
    padding: 8px 0;
    outline: 0;
}
QListWidget#nav::item {
    color: #b9c2cf;
    padding: 10px 16px;
    border-radius: 8px;
    margin: 2px 8px;
}
QListWidget#nav::item:hover {
    background: #1a212b;
    color: #ffffff;
}
QListWidget#nav::item:selected {
    background: #1e3a5f;
    color: #ffffff;
    border-left: 3px solid #3b82f6;
    padding-left: 13px;
}

/* Cards */
QFrame#card {
    background: #161b22;
    border: 1px solid #232c38;
    border-radius: 12px;
}
QLabel#cardTitle {
    font-size: 14px;
    font-weight: 600;
    color: #f0f3f8;
}
QLabel#sectionLabel {
    font-size: 12px;
    font-weight: 600;
    color: #8b97a7;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
QLabel#fieldLabel {
    color: #aeb8c6;
}
QLabel#bigValue {
    font-size: 22px;
    font-weight: 700;
    color: #f0f3f8;
}
QLabel#muted {
    color: #7b8696;
}
QLabel#titleText {
    font-size: 18px;
    font-weight: 700;
    color: #ffffff;
}

/* Buttons */
QPushButton {
    background: #222b38;
    color: #e7ebf2;
    border: 1px solid #2d3848;
    border-radius: 9px;
    padding: 8px 14px;
}
QPushButton:hover { background: #2a3442; }
QPushButton:pressed { background: #303d4e; }
QPushButton:disabled { color: #5b6675; background: #1a2029; }

QPushButton#primary {
    background: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#primary:hover { background: #1d6fe0; }
QPushButton#danger {
    background: #3a1d24;
    border: 1px solid #6b2735;
    color: #ff8e9e;
}
QPushButton#danger:hover { background: #4a2530; }

QPushButton#seg {
    border-radius: 8px;
    padding: 7px 10px;
    background: #1b2230;
    border: 1px solid #2a3340;
}
QPushButton#seg:checked {
    background: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

/* Combo box */
QComboBox {
    background: #1b2230;
    border: 1px solid #2a3340;
    border-radius: 8px;
    padding: 6px 10px;
    min-width: 120px;
}
QComboBox:hover { border: 1px solid #3a475a; }
QComboBox QAbstractItemView {
    background: #161b22;
    border: 1px solid #2a3340;
    selection-background-color: #1e3a5f;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background: #2a3340;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: #cfe0ff;
    border-radius: 8px;
    border: 2px solid #3b82f6;
}
QSlider::handle:horizontal:hover { background: #ffffff; }

/* Progress bars (battery) */
QProgressBar {
    border: 1px solid #2a3340;
    border-radius: 6px;
    background: #11161d;
    text-align: center;
    color: #e7ebf2;
    height: 18px;
}
QProgressBar::chunk {
    background: #3b82f6;
    border-radius: 5px;
}

/* Tables */
QTableWidget {
    background: #11161d;
    gridline-color: #232c38;
    border: 1px solid #232c38;
    border-radius: 8px;
}
QHeaderView::section {
    background: #161b22;
    color: #8b97a7;
    border: none;
    padding: 6px;
    font-weight: 600;
}
QTableWidget::item:selected { background: #1e3a5f; }

/* Text edit / log */
QPlainTextEdit {
    background: #0b0e13;
    border: 1px solid #232c38;
    border-radius: 8px;
    color: #c7d0dc;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}

QStatusBar { background: #11161d; color: #aeb8c6; }
QStatusBar::item { border: none; }

QScrollArea { border: none; background: transparent; }
QLabel#hint { color: #7b8696; }
"""

# Light, OS-native structural sheet --------------------------------------
# Only layout/structure elements are styled; interactive controls (buttons,
# sliders, combo boxes, progress bars) are left to the native Windows theme.
STYLE_NATIVE = """
QWidget {
    font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
    font-size: 13px;
}
QMainWindow, QWidget#central {
    background: #f3f3f3;
}

QListWidget#nav {
    background: #e9eef5;
    border: none;
    border-right: 1px solid #cdd6e0;
    padding: 8px 0;
    outline: 0;
}
QListWidget#nav::item {
    color: #2b3340;
    padding: 10px 16px;
    border-radius: 8px;
    margin: 2px 8px;
}
QListWidget#nav::item:hover {
    background: #dde6f1;
}
QListWidget#nav::item:selected {
    background: #cfe0f5;
    color: #10243e;
    border-left: 3px solid #2563eb;
    padding-left: 13px;
}

QFrame#card {
    background: #ffffff;
    border: 1px solid #d3dae3;
    border-radius: 10px;
}
QLabel#cardTitle {
    font-size: 14px;
    font-weight: 600;
    color: #1f2733;
}
QLabel#sectionLabel {
    font-size: 12px;
    font-weight: 600;
    color: #6b7686;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
QLabel#fieldLabel {
    color: #4a5562;
}
QLabel#bigValue {
    font-size: 22px;
    font-weight: 700;
    color: #1f2733;
}
QLabel#muted {
    color: #6b7686;
}
QLabel#titleText {
    font-size: 18px;
    font-weight: 700;
    color: #1f2733;
}

QStatusBar { background: #e9eef5; color: #4a5562; }
QStatusBar::item { border: none; }

QScrollArea { border: none; background: transparent; }
QLabel#hint { color: #6b7686; }
"""


# --------------------------------------------------------------------------
# Layout helpers
# --------------------------------------------------------------------------


def labeled(label_text: str, control: QWidget, *, stretch: bool = False) -> QWidget:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    lbl = QLabel(label_text)
    lbl.setObjectName("fieldLabel")
    lbl.setMinimumWidth(120)
    row.addWidget(lbl)
    if stretch:
        row.addWidget(control, 1)
    else:
        row.addWidget(control)
    wrap = QWidget()
    wrap.setLayout(row)
    return wrap


def hbox(*widgets, spacing: int = 10, stretch_last: bool = False) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    for w in widgets:
        if w is None:
            continue
        if stretch_last and w is widgets[-1]:
            layout.addWidget(w, 1)
        else:
            layout.addWidget(w)
    return layout


def vbox(*widgets, spacing: int = 10, margin: int = 0) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(margin, margin, margin, margin)
    for w in widgets:
        if w is None:
            continue
        layout.addWidget(w)
    return layout


class Card(QFrame):
    """A rounded container with an optional title."""

    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        if title:
            t = QLabel(title)
            t.setObjectName("cardTitle")
            root.addWidget(t)
        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(10)
        root.addLayout(self._body)

    def body(self) -> QVBoxLayout:
        return self._body

    def add(self, *items) -> None:
        for w in items:
            if isinstance(w, QVBoxLayout):
                self._body.addLayout(w)
            else:
                self._body.addWidget(w)


class SectionLabel(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionLabel")


# --------------------------------------------------------------------------
# Custom controls
# --------------------------------------------------------------------------


class BatteryBar(QWidget):
    """Native progress-bar battery indicator with an optional charging note."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(True)
        self._note = QLabel("")
        self._note.setObjectName("muted")
        self._note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._bar)
        layout.addWidget(self._note)

    def set_level(self, level: int, charging: bool = False) -> None:
        level = max(0, min(100, int(level)))
        self._bar.setValue(level)
        self._bar.setFormat(f"{level}%" if not charging else f"{level}%  ·  充电中")
        self._note.setText("充电中" if charging else "")


class Switch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on = False
        self.setFixedSize(48, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._on

    def setChecked(self, value: bool, *, notify: bool = False) -> None:
        if self._on == value:
            return
        self._on = value
        self.update()
        if notify:
            self.toggled.emit(value)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        self.setChecked(not self._on, notify=True)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        r = h / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#3a4150") if not self._on else QColor("#2563eb")))
        p.drawRoundedRect(self.rect(), r, r)

        knob = h - 8
        x = 4 if not self._on else self.width() - knob - 4
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(x + knob / 2, h / 2), knob / 2, knob / 2)


class SegmentedControl(QWidget):
    changed = Signal(int)

    def __init__(
        self, options, parent: QWidget | None = None  # list[(text, value)]
    ) -> None:
        super().__init__(parent)
        self._options = list(options)
        self._value = options[0][1] if options else 0
        self._buttons: list[QPushButton] = []
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for i, (text, value) in enumerate(options):
            btn = QPushButton(text)
            btn.setObjectName("seg")
            btn.setCheckable(True)
            self._group.addButton(btn, i)
            layout.addWidget(btn)
            self._buttons.append(btn)
        self._group.buttonClicked.connect(self._on_click)
        self._refresh()

    def _on_click(self, button) -> None:  # noqa: ANN001
        self._value = button.property("segValue")
        self._refresh()
        self.changed.emit(self._value)

    def _refresh(self) -> None:
        for btn in self._buttons:
            btn.setChecked(btn.property("segValue") == self._value)

    def set_options(self, options) -> None:
        self._options = list(options)
        old = self._value
        # rebuild buttons
        for btn in self._buttons:
            self._group.removeButton(btn)
            btn.deleteLater()
        self._buttons.clear()
        # clear layout
        while self.layout().count():
            item = self.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, (text, value) in enumerate(options):
            btn = QPushButton(text)
            btn.setObjectName("seg")
            btn.setCheckable(True)
            btn.setProperty("segValue", value)
            self._group.addButton(btn, i)
            self.layout().addWidget(btn)
            self._buttons.append(btn)
        self._group.buttonClicked.connect(self._on_click)
        self._value = old if any(v == old for _, v in options) else options[0][1]
        self._refresh()

    def setValue(self, value: int, *, notify: bool = False) -> None:
        if self._value == value:
            return
        self._value = value
        self._refresh()
        if notify:
            self.changed.emit(value)

    def set_enabled(self, enabled: bool) -> None:
        for btn in self._buttons:
            btn.setEnabled(enabled)


class SliderRow(QWidget):
    valueChanged = Signal(int)

    def __init__(
        self,
        label: str,
        minimum: int,
        maximum: int,
        value: int = 0,
        *,
        formatter=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._formatter = formatter or (lambda v: str(v))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setObjectName("fieldLabel")
        lbl.setMinimumWidth(120)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(minimum, maximum)
        self._slider.setValue(value)
        self._value = QLabel(self._formatter(value))
        self._value.setMinimumWidth(52)
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(lbl)
        layout.addWidget(self._slider, 1)
        layout.addWidget(self._value)
        self._slider.valueChanged.connect(self._on_change)

    def _on_change(self, v: int) -> None:
        self._value.setText(self._formatter(v))
        self.valueChanged.emit(v)

    def set_value(self, v: int, *, notify: bool = False) -> None:
        if self._slider.value() == v:
            return
        self._slider.setValue(v)
        self._value.setText(self._formatter(v))
        if notify:
            self.valueChanged.emit(v)

    def set_enabled(self, enabled: bool) -> None:
        self._slider.setEnabled(enabled)


class EnumCombo(QWidget):
    valueChanged = Signal(int)

    def __init__(
        self,
        label: str,
        options,  # list[(text, value)]
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._options = list(options)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setObjectName("fieldLabel")
        lbl.setMinimumWidth(120)
        self._combo = QComboBox()
        for text, value in options:
            self._combo.addItem(text, value)
        layout.addWidget(lbl)
        layout.addWidget(self._combo, 1)
        self._combo.currentIndexChanged.connect(self._on_change)

    def _on_change(self, index: int) -> None:
        value = self._combo.itemData(index)
        if value is None:
            return
        self.valueChanged.emit(int(value))

    def set_options(self, options) -> None:
        self._options = list(options)
        self._combo.blockSignals(True)
        self._combo.clear()
        for text, value in options:
            self._combo.addItem(text, value)
        self._combo.blockSignals(False)

    def set_value(self, value: int) -> None:
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == value:
                self._combo.setCurrentIndex(i)
                return

    def set_enabled(self, enabled: bool) -> None:
        self._combo.setEnabled(enabled)
