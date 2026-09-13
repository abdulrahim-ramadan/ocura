from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from ocura.application.presenter import TICK_SECONDS, BreakPresenter, SessionView


class TickDriver(QObject):
    """Delivers a pulse. Decides nothing.

    The presenter owns what a tick means; Qt owns only the delivery. A pulse
    never means "one second has passed" — Qt timers coalesce under load, stall
    behind modal dialogs and drift across sleep — so every duration is re-read
    from the monotonic clock on each pulse. A late, dropped or doubled pulse
    costs refresh latency and nothing else.
    """

    viewChanged = Signal(object)

    def __init__(self, presenter: BreakPresenter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._timer = QTimer(self)
        self._timer.setInterval(int(TICK_SECONDS * 1000))
        self._timer.timeout.connect(self._pulse)

    @property
    def presenter(self) -> BreakPresenter:
        return self._presenter

    def start(self) -> None:
        self._emit(self._presenter.start())
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._emit(self._presenter.stop())

    def toggle_paused(self) -> None:
        self._emit(self._presenter.toggle_paused())

    def take_break_now(self) -> None:
        self._emit(self._presenter.take_break_now())

    def refresh(self) -> None:
        self._emit(self._presenter.view())

    def _pulse(self) -> None:
        self._emit(self._presenter.tick())

    def _emit(self, view: SessionView) -> None:
        self.viewChanged.emit(view)
