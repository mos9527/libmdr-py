"""Qt binding compatibility shim.

The example works with either PySide6 or PyQt6 — the first one that imports
is used, so users only need one of them installed.  All other modules import
their Qt symbols from here.
"""

from __future__ import annotations

import importlib

_BINDINGS = ("PySide6", "PyQt6")
_qt = None
for _name in _BINDINGS:
    try:
        importlib.import_module(_name)
        _qt = _name
        break
    except Exception:  # noqa: BLE001 - try the next candidate
        continue

if _qt is None:
    raise ImportError(
        "需要一个 Qt 绑定才能运行此示例。请安装其中之一：\n"
        "    pip install PySide6\n"
        "    pip install PyQt6"
    )

if _qt == "PySide6":
    from PySide6.QtCore import (  # noqa: F401
        QEvent,
        QMargins,
        QObject,
        QPoint,
        QPointF,
        QRect,
        QRectF,
        QSettings,
        QSize,
        QThread,
        QTimer,
        Qt,
        Signal,
        Slot,
    )
    from PySide6.QtGui import (  # noqa: F401
        QAction,
        QColor,
        QDesktopServices,
        QFont,
        QFontMetrics,
        QIcon,
        QIntValidator,
        QMouseEvent,
        QPaintEvent,
        QPainter,
        QPen,
        QBrush,
        QPixmap,
        QPolygonF,
        QResizeEvent,
        QWheelEvent,
    )
    from PySide6.QtWidgets import (  # noqa: F401
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QComboBox,
        QFrame,
        QGroupBox,
        QHeaderView,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMenuBar,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSpacerItem,
        QStackedWidget,
        QStatusBar,
        QCheckBox,
        QStyleFactory,
        QTableWidget,
        QTableWidgetItem,
        QPlainTextEdit,
        QToolBar,
        QVBoxLayout,
        QWidget,
        QGridLayout,
    )
else:  # PyQt6
    from PyQt6.QtCore import (  # noqa: F401
        QEvent,
        QMargins,
        QObject,
        QPoint,
        QPointF,
        QRect,
        QRectF,
        QSettings,
        QSize,
        QThread,
        QTimer,
        Qt,
        pyqtSignal as Signal,
        pyqtSlot as Slot,
    )
    from PyQt6.QtGui import (  # noqa: F401
        QAction,
        QColor,
        QDesktopServices,
        QFont,
        QFontMetrics,
        QIcon,
        QIntValidator,
        QMouseEvent,
        QPaintEvent,
        QPainter,
        QPen,
        QBrush,
        QPixmap,
        QPolygonF,
        QResizeEvent,
        QWheelEvent,
    )
    from PyQt6.QtWidgets import (  # noqa: F401
        QAbstractItemView,
        QApplication,
        QButtonGroup,
        QComboBox,
        QFrame,
        QGroupBox,
        QHeaderView,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMenuBar,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSpacerItem,
        QStackedWidget,
        QStatusBar,
        QCheckBox,
        QStyleFactory,
        QTableWidget,
        QTableWidgetItem,
        QPlainTextEdit,
        QToolBar,
        QVBoxLayout,
        QWidget,
        QGridLayout,
    )

QT_BINDING = _qt
