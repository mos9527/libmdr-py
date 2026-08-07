"""Small reusable widgets for the libmdr TUI.

Textual ships no slider widget, so a minimal one lives here together with a
``Select`` subclass that keeps track of its own option list (so options can be
swapped as device capabilities are discovered).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Select

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from rich.console import RenderableType


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


class Slider(Widget):
    """A one-line horizontal slider driven by arrow keys or the mouse."""

    can_focus = True

    COMPONENT_CLASSES = {
        "slider--filled",
        "slider--track",
        "slider--thumb",
        "slider--value",
    }

    DEFAULT_CSS = """
    Slider {
        height: 1;
        width: 1fr;
    }
    Slider > .slider--filled { color: $success; }
    Slider > .slider--track { color: $foreground 30%; }
    Slider > .slider--thumb { color: $accent; text-style: bold; }
    Slider > .slider--value { color: $foreground 70%; }
    Slider:focus > .slider--thumb { color: $warning; text-style: bold; }
    Slider:disabled { color: $foreground 30%; }
    """

    BINDINGS = [
        Binding("left,h", "nudge(-1)", "Decrease", show=False),
        Binding("right,l", "nudge(1)", "Increase", show=False),
        Binding("down,j", "nudge(-1)", "Decrease", show=False),
        Binding("up,k", "nudge(1)", "Increase", show=False),
        Binding("home", "jump(0)", "Minimum", show=False),
        Binding("end", "jump(1)", "Maximum", show=False),
    ]

    class Changed(Message):
        """Posted when the user moves the slider."""

        def __init__(self, slider: Slider, value: int) -> None:
            super().__init__()
            self.slider = slider
            self.value = value

        @property
        def control(self) -> Slider:
            return self.slider

    def __init__(
        self,
        minimum: int = 0,
        maximum: int = 100,
        value: int = 0,
        *,
        step: int = 1,
        formatter: Callable[[int], str] | None = None,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(id=id, classes=classes, disabled=disabled)
        self._minimum = minimum
        self._maximum = maximum
        self._step = max(1, step)
        self._formatter = formatter or (lambda v: str(v))
        self._value = _clamp(value, minimum, maximum)

    # -- state -----------------------------------------------------------

    @property
    def value(self) -> int:
        return self._value

    def set_range(self, minimum: int, maximum: int) -> None:
        if (minimum, maximum) == (self._minimum, self._maximum):
            return
        self._minimum = minimum
        self._maximum = maximum
        self._value = _clamp(self._value, minimum, maximum)
        self.refresh()

    def set_value(self, value: int, *, notify: bool = False) -> None:
        """Set the value; only posts :class:`Changed` when ``notify`` is set."""
        value = _clamp(int(value), self._minimum, self._maximum)
        if value == self._value:
            return
        self._value = value
        self.refresh()
        if notify:
            self.post_message(self.Changed(self, value))

    # -- interaction -----------------------------------------------------

    def action_nudge(self, delta: int) -> None:
        self.set_value(self._value + delta * self._step, notify=True)

    def action_jump(self, ratio: float) -> None:
        target = self._minimum + (self._maximum - self._minimum) * ratio
        self.set_value(int(round(target)), notify=True)

    def _value_from_x(self, x: int) -> int:
        bar_width = max(1, self._bar_width())
        ratio = _clamp(x, 0, bar_width - 1) / max(1, bar_width - 1)
        span = self._maximum - self._minimum
        return int(round(self._minimum + ratio * span))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.focus()
        self.capture_mouse()
        self.set_value(self._value_from_x(event.x), notify=True)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.app.mouse_captured is self:
            self.set_value(self._value_from_x(event.x), notify=True)

    def on_mouse_up(self, _event: events.MouseUp) -> None:
        if self.app.mouse_captured is self:
            self.release_mouse()

    # -- rendering -------------------------------------------------------

    def _suffix(self) -> str:
        return f" {self._formatter(self._value)}"

    def _bar_width(self) -> int:
        width = self.size.width or 24
        return max(4, width - len(self._suffix()))

    def render(self) -> RenderableType:
        bar_width = self._bar_width()
        span = self._maximum - self._minimum
        ratio = 0.0 if span <= 0 else (self._value - self._minimum) / span
        thumb = int(round(ratio * (bar_width - 1)))

        filled = self.get_component_rich_style("slider--filled")
        track = self.get_component_rich_style("slider--track")
        knob = self.get_component_rich_style("slider--thumb")
        value_style = self.get_component_rich_style("slider--value")

        text = Text(no_wrap=True, overflow="crop")
        if thumb:
            text.append("━" * thumb, filled)
        text.append("●", knob)
        remaining = bar_width - thumb - 1
        if remaining > 0:
            text.append("─" * remaining, track)
        text.append(self._suffix(), value_style)
        return text


class EnumSelect(Select):
    """``Select`` that remembers its options and never raises on unknown values."""

    def __init__(
        self,
        options: Sequence[tuple[str, int]] = (),
        *,
        id: str | None = None,  # noqa: A002
        classes: str | None = None,
        disabled: bool = False,
        prompt: str = "n/a",
    ) -> None:
        self._current_options: list[tuple[str, int]] = list(options)
        super().__init__(
            self._current_options,
            prompt=prompt,
            allow_blank=True,
            id=id,
            classes=classes,
            disabled=disabled,
        )

    def update_options(self, options: Sequence[tuple[str, int]]) -> None:
        options = list(options)
        if options == self._current_options:
            return
        self._current_options = options
        keep = self.value
        self.set_options(options)
        if keep is not Select.BLANK and any(value == keep for _, value in options):
            self.value = keep

    def select_value(self, value: int | None) -> None:
        """Select ``value`` without raising when it is not a known option."""
        if value is not None and any(known == value for _, known in self._current_options):
            if self.value != value:
                self.value = value
        elif self.value is not Select.BLANK:
            self.value = Select.BLANK
