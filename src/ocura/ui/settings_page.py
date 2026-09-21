"""The Settings page. Edits a Settings, refuses to invent one.

Two rules shape everything here.

**Nothing is silently clamped.** The spin boxes are given ranges far wider than
anything Ocura will accept, so the number in the box stays the number the user
typed and the refusal comes from `Settings.validate()` with a sentence
attached. A spin box that quietly snaps 5 to 60 has told the user their
configuration is something it is not, and they will not find out until a break
arrives at the wrong time.

**A refused value is not reverted either.** The box keeps what was typed, the
message says what is wrong, and the previous setting stays in force until
something valid replaces it. Snapping the control back would throw away the
edit in progress and leave the user retyping from scratch to find out what else
is wrong with it.

Each control commits on its own — there is no Save button — because every
setting here is independent and a form that has to be submitted is a form that
can be abandoned half-applied. What the running session does with the change is
`BreakPresenter.apply`'s business.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ocura.application.autostart import Autostart, AutostartUnavailable, NoAutostart
from ocura.application.settings import (
    DEFAULTS,
    LANGUAGE_NAMES,
    SYSTEM_LABEL,
    SYSTEM_LANGUAGE,
    THEME_NAMES,
    InvalidSettings,
    Settings,
    language_label,
)
from ocura.ui.theme import LAYOUT, SPACING
from ocura.ui.views import _card, _label

logger = logging.getLogger(__name__)

#: Wide enough that Ocura's own limits are always the ones doing the refusing.
#: If Qt clamps first the user gets a number they did not type and no reason
#: for it, which is the one thing this page is built not to do.
SPIN_CEILING = 100_000

#: Source text for the theme names. Translated on every retranslate; the
#: stored value is always the untranslated key.
THEME_LABELS = {"dark": "Dark", "light": "Light"}


def _spin(value: int) -> QSpinBox:
    box = QSpinBox()
    box.setObjectName("SettingSpin")
    box.setRange(0, SPIN_CEILING)
    box.setValue(value)
    box.setKeyboardTracking(False)  # commit on Enter or focus-out, not per digit
    box.setAlignment(Qt.AlignmentFlag.AlignRight)
    # No steppers. Qt draws them inside the field, over the suffix, and the
    # only way to keep "20 min" legible next to them is a field wide enough to
    # look like a text area. These are numbers people set once and type; the
    # arrow keys and the wheel still step them.
    box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    return box


class SettingRow(QWidget):
    """One control, its label, its explanation, and the room for its refusal."""

    def __init__(self, title: str, explanation: str, control: QWidget, suffix: str = "") -> None:
        super().__init__()

        self._source_title = title
        self._source_explanation = explanation
        self._source_suffix = suffix
        self._control = control
        self._problem = _label("", "SettingProblem")
        self._problem.hide()

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.setSpacing(SPACING.m)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(SPACING.xs)
        self._title = _label("", "SettingTitle")
        self._note = _label("", "SettingNote")
        text.addWidget(self._title)
        text.addWidget(self._note)
        heading.addLayout(text, 1)
        heading.addWidget(control, 0, Qt.AlignmentFlag.AlignTop)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(SPACING.s)
        column.addLayout(heading)
        column.addWidget(self._problem)
        self.retranslate()

    def retranslate(self) -> None:
        self._title.setText(self.tr(self._source_title))
        self._note.setText(self.tr(self._source_explanation))
        if self._source_suffix and isinstance(self._control, QSpinBox):
            # The unit belongs to the language, not to the number. German uses
            # "Min."; Arabic uses its own word and reads the other way round,
            # which Qt handles once the suffix is a translated string rather
            # than a constant baked in at construction.
            self._control.setSuffix(self.tr(self._source_suffix))

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(event)

    def show_problem(self, message: str) -> None:
        self._problem.setText(message)
        self._problem.show()

    def clear_problem(self) -> None:
        self._problem.clear()
        self._problem.hide()


class SettingsPage(QWidget):
    """Renders and edits a Settings. Persisting it is the application's job."""

    #: A validated Settings the user has just asked for. Emitted only when it
    #: is honourable, so nothing downstream has to validate a second time.
    settingsChanged = Signal(object)

    def __init__(
        self,
        settings: Settings | None = None,
        autostart: Autostart | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings or DEFAULTS
        self._autostart = autostart or NoAutostart()
        self._loading = False

        self._interval = _spin(20)
        self._duration = _spin(20)
        self._warning = _spin(60)
        self._idle = _spin(120)

        self._theme = QComboBox()
        self._theme.setObjectName("SettingChoice")
        for name in THEME_NAMES:
            self._theme.addItem(THEME_LABELS[name], name)

        self._tips = QCheckBox()
        self._tips.setObjectName("SettingToggle")
        self._autostart_box = QCheckBox()
        self._autostart_box.setObjectName("SettingToggle")

        self._language = QComboBox()
        self._language.setObjectName("SettingChoice")
        for name in (SYSTEM_LANGUAGE, *LANGUAGE_NAMES):
            self._language.addItem("", name)

        self._rows: dict[str, SettingRow] = {}
        self._build()
        self._connect()
        self.retranslate()
        self.load(self._settings)

    # --- construction ------------------------------------------------------

    #: field, heading, explanation, control, spin-box suffix.
    def _rows_spec(self):
        return (
            (
                "Rhythm",
                (
                    (
                        "focus_interval",
                        "Time between breaks",
                        "How long a focus block runs before Ocura offers a break.",
                        self._interval,
                        " min",
                    ),
                    (
                        "break_duration",
                        "Break length",
                        "How long the break screen stays up. Twenty seconds is the "
                        "guideline Ocura is built around.",
                        self._duration,
                        " sec",
                    ),
                    (
                        "pre_break_warning",
                        "Warning lead time",
                        "How long before a break Ocura says one is coming, so you can "
                        "finish your thought.",
                        self._warning,
                        " sec",
                    ),
                ),
            ),
            (
                "When not to interrupt",
                (
                    (
                        "idle_threshold",
                        "Idle threshold",
                        "How long without keyboard or mouse before Ocura decides you are "
                        "away and waits rather than offering a break to an empty chair.",
                        self._idle,
                        " sec",
                    ),
                ),
            ),
            (
                "Language and appearance",
                (
                    (
                        "language",
                        "Language",
                        "Ocura follows your Windows language unless you choose one here.",
                        self._language,
                        "",
                    ),
                    (
                        "theme",
                        "Theme",
                        "The dark and light themes for the main window.",
                        self._theme,
                        "",
                    ),
                    (
                        "tips",
                        "Break-screen evidence",
                        "The sourced line at the foot of the break screen.",
                        self._tips,
                        "",
                    ),
                    (
                        "autostart",
                        "Start with Windows",
                        "Adds Ocura to your sign-in startup list. You can also remove it "
                        "from Task Manager, under Startup.",
                        self._autostart_box,
                        "",
                    ),
                ),
            ),
        )

    def _build(self) -> None:
        self._sections: list[tuple[object, str]] = []
        cards = [self._section(title, rows) for title, rows in self._rows_spec()]

        content = QWidget()
        content.setObjectName("Content")
        content.setMaximumWidth(LAYOUT.content_max_width)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._headline = _label("", "Headline")
        self._subheading = _label("", "Detail")

        column = QVBoxLayout(content)
        column.setContentsMargins(SPACING.xs, 0, SPACING.xs, 0)
        column.setSpacing(SPACING.m)
        column.addWidget(self._headline)
        column.addWidget(self._subheading)
        for card in cards:
            column.addWidget(card)
        column.addStretch(1)

        scroller = QScrollArea()
        scroller.setObjectName("Page")
        scroller.setWidget(content)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        root = QHBoxLayout(self)
        root.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        root.addWidget(scroller, 1)
        root.addStretch(0)

    def _section(self, title: str, rows) -> QWidget:
        card = _card()
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACING.lg, SPACING.m, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.m)
        heading_label = _label("", "SectionTitle")
        self._sections.append((heading_label, title))
        layout.addWidget(heading_label)
        for field, heading, explanation, control, suffix in rows:
            row = SettingRow(heading, explanation, control, suffix)
            self._rows[field] = row
            layout.addWidget(row)
        return card

    def _connect(self) -> None:
        self._interval.valueChanged.connect(self._commit)
        self._duration.valueChanged.connect(self._commit)
        self._warning.valueChanged.connect(self._commit)
        self._idle.valueChanged.connect(self._commit)
        self._theme.currentIndexChanged.connect(self._commit)
        self._language.currentIndexChanged.connect(self._commit)
        self._tips.toggled.connect(self._commit)
        self._autostart_box.toggled.connect(self._commit_autostart)

    def retranslate(self) -> None:
        self._headline.setText(self.tr("Settings"))
        self._subheading.setText(
            self.tr(
                "Changes apply to the session you are in now. Nothing here is saved "
                "anywhere but on this machine."
            )
        )
        for label, title in self._sections:
            label.setText(self.tr(title))
        for row in self._rows.values():
            row.retranslate()

        self._tips.setText(self.tr("Show the evidence line on the break screen"))
        self._autostart_box.setText(self.tr("Start Ocura when I sign in to Windows"))

        # The combo boxes hold untranslated keys as data and translated text as
        # labels, so relabelling never changes what is selected or what is
        # saved.
        self._loading = True
        try:
            for index in range(self._theme.count()):
                self._theme.setItemText(index, self.tr(THEME_LABELS[self._theme.itemData(index)]))
            for index in range(self._language.count()):
                name = self._language.itemData(index)
                self._language.setItemText(index, language_label(name, self.tr(SYSTEM_LABEL)))
        finally:
            self._loading = False

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate()
        super().changeEvent(event)

    # --- rendering ---------------------------------------------------------

    def load(self, settings: Settings) -> None:
        """Show these settings without treating the update as an edit."""
        self._settings = settings
        self._loading = True
        try:
            self._interval.setValue(round(settings.focus_interval / 60))
            self._duration.setValue(round(settings.break_duration))
            self._warning.setValue(round(settings.pre_break_warning))
            self._idle.setValue(round(settings.idle_threshold))
            self._theme.setCurrentIndex(max(0, self._theme.findData(settings.theme)))
            self._language.setCurrentIndex(max(0, self._language.findData(settings.language)))
            self._tips.setChecked(settings.tips)
            # What the machine will actually do at the next sign-in, which is
            # not always what the stored setting says: another startup manager
            # or a copied profile can disagree, and the registry wins because
            # the registry is what runs.
            self._autostart_box.setChecked(
                self._autostart.is_enabled() if self._autostart.available else settings.autostart
            )
            self._autostart_box.setEnabled(self._autostart.available)
            if not self._autostart.available:
                self._rows["autostart"].show_problem(
                    "Ocura cannot manage startup entries on this machine."
                )
        finally:
            self._loading = False
        for row in self._rows.values():
            if row is not self._rows["autostart"] or self._autostart.available:
                row.clear_problem()

    # --- editing -----------------------------------------------------------

    def _candidate(self) -> Settings:
        return self._settings.replace(
            focus_interval=float(self._interval.value() * 60),
            break_duration=float(self._duration.value()),
            pre_break_warning=float(self._warning.value()),
            idle_threshold=float(self._idle.value()),
            theme=self._theme.currentData() or self._settings.theme,
            # currentData() is "" for "follow Windows", which is a real value
            # here rather than a missing one — so no `or` fallback.
            language=self._language.currentData(),
            tips=self._tips.isChecked(),
        )

    def _commit(self) -> None:
        if self._loading:
            return
        try:
            settings = self._candidate().validate()
        except InvalidSettings as exc:
            # The typed value stays where it is. See the module docstring: a
            # control that snaps back has thrown away the edit and told the
            # user nothing they can act on.
            self._show_problem(exc)
            return

        self._clear_problems()
        self._settings = settings
        self.settingsChanged.emit(settings)

    def _commit_autostart(self, enabled: bool) -> None:
        """Ask Windows first, and only then believe the checkbox.

        The registry is what decides whether Ocura starts, so a failure here
        has to put the control back — otherwise the page is showing a promise
        the machine has not made.
        """
        if self._loading:
            return
        row = self._rows["autostart"]
        try:
            self._autostart.set_enabled(enabled)
        except AutostartUnavailable as exc:
            logger.warning("could not change the startup entry: %s", exc)
            row.show_problem(str(exc))
            self._loading = True
            try:
                self._autostart_box.setChecked(not enabled)
            finally:
                self._loading = False
            return

        row.clear_problem()
        self._settings = self._settings.replace(autostart=enabled)
        self.settingsChanged.emit(self._settings)

    def _show_problem(self, exc: InvalidSettings) -> None:
        self._clear_problems()
        row = self._rows.get(exc.field)
        # Falls back to the interval's row rather than dropping the message: a
        # refusal the user cannot see is a control that appears to do nothing.
        (row or self._rows["focus_interval"]).show_problem(str(exc))

    def _clear_problems(self) -> None:
        for field, row in self._rows.items():
            if field == "autostart" and not self._autostart.available:
                continue
            row.clear_problem()

    # --- for the sidebar shortcut -------------------------------------------

    def set_theme(self, name: str) -> None:
        """The sidebar's toggle, arriving as an edit to this page.

        `docs/architecture.md` said the sidebar control would become a shortcut
        to the real setting in P5. This is that: one place decides what a theme
        change means, and the footer button is a way of asking for it.
        """
        index = self._theme.findData(name)
        if index >= 0 and index != self._theme.currentIndex():
            self._theme.setCurrentIndex(index)
