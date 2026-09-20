"""The three first-run screens, as one modal dialog.

A dialog rather than a page in the main window, because this is the one thing
in Ocura that is deliberately in the way: it is asked once, it is short, and
what follows it depends on the answers. The main window opens behind it already
configured.

It renders an `OnboardingView` and sends back answers. Every sentence on screen
comes from `ocura.application.onboarding`, which is where the language is
decided and tested.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ocura.application.onboarding import Onboarding, OnboardingView, Step
from ocura.application.settings import InvalidSettings, Settings
from ocura.ui.theme import SPACING
from ocura.ui.views import _label

DIALOG_WIDTH = 620
DIALOG_HEIGHT = 480

#: The custom option on the rhythm screen. Not a spin box: first run is three
#: questions with obvious answers, and the place to type a number is Settings,
#: where every other number already lives and the refusals are already handled.
CUSTOM_LABEL = "Something else — I will set it in Settings"


class OnboardingDialog(QDialog):
    """Three screens. Ends in a Settings, or in nothing at all if dismissed."""

    #: The finished settings. Emitted once, on the last screen's button.
    completed = Signal(object)

    def __init__(self, flow: Onboarding | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._flow = flow or Onboarding()

        self.setWindowTitle("Welcome to Ocura")
        self.setObjectName("Onboarding")
        self.setModal(True)
        self.resize(DIALOG_WIDTH, DIALOG_HEIGHT)

        self._position = _label("", "OnboardingStep")
        self._title = _label("", "OnboardingTitle")
        self._body = _label("", "OnboardingBody")
        self._note = _label("", "OnboardingNote")

        self._choices = QWidget()
        self._choice_layout = QVBoxLayout(self._choices)
        self._choice_layout.setContentsMargins(0, 0, 0, 0)
        self._choice_layout.setSpacing(SPACING.s)
        self._rhythms = QButtonGroup(self)
        self._autostart_yes = QRadioButton("Yes, start Ocura when I sign in")
        self._autostart_no = QRadioButton("No, I will start it myself")
        for button in (self._autostart_yes, self._autostart_no):
            button.setObjectName("OnboardingChoice")

        self._back = QPushButton("Back")
        self._advance = QPushButton("Next")
        self._advance.setObjectName("Primary")
        self._advance.setDefault(True)

        self._build()
        self._connect()
        self.render(self._flow.view())

    # No fade between screens. Fading the dialog itself means compositing a
    # top-level window against nothing, which paints the platform's default
    # grey under everything for the length of the animation; and a full-window
    # flash on each Next is the kind of motion the product's own policy exists
    # to refuse. The three screens change instantly.

    def _build(self) -> None:
        for label in (self._body, self._note):
            label.setWordWrap(True)
        self._title.setWordWrap(True)

        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(SPACING.sm)
        text.addWidget(self._position)
        text.addWidget(self._title)
        text.addWidget(self._body)
        text.addWidget(self._choices)
        text.addWidget(self._note)
        text.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(SPACING.s)
        buttons.addWidget(self._back)
        buttons.addStretch(1)
        buttons.addWidget(self._advance)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING.xl, SPACING.xl, SPACING.xl, SPACING.lg)
        root.setSpacing(SPACING.lg)
        root.addLayout(text, 1)
        root.addLayout(buttons)

        self._choices.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _connect(self) -> None:
        self._back.clicked.connect(self._on_back)
        self._advance.clicked.connect(self._on_advance)
        self._autostart_yes.toggled.connect(self._on_autostart)

    # --- rendering ---------------------------------------------------------

    def render(self, view: OnboardingView) -> None:
        self._position.setText(f"{view.position} of {view.total}")
        self._title.setText(view.title)
        self._body.setText(view.body)
        self._note.setText(view.note)
        self._back.setVisible(view.can_go_back)
        self._advance.setText(view.advance_label)

        self._clear_choices()
        if view.step is Step.RHYTHM:
            self._build_rhythms(view)
        elif view.step is Step.AUTOSTART:
            self._build_autostart(view)

    def _clear_choices(self) -> None:
        while self._choice_layout.count():
            item = self._choice_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Unparented before the deferred delete, or it keeps painting
                # at its old geometry over the screen that replaced it.
                widget.setParent(None)
        for button in self._rhythms.buttons():
            self._rhythms.removeButton(button)
        self._choices.setVisible(False)

    def _build_rhythms(self, view: OnboardingView) -> None:
        for index, minutes in enumerate(view.rhythm_choices):
            button = QRadioButton(f"Every {minutes} minutes")
            button.setObjectName("OnboardingChoice")
            button.setChecked(minutes == view.chosen_minutes)
            self._rhythms.addButton(button, minutes)
            self._choice_layout.addWidget(button)
            if index == 0:
                button.setToolTip("The 20-20-20 guideline")

        custom = QRadioButton(CUSTOM_LABEL)
        custom.setObjectName("OnboardingChoice")
        custom.setChecked(view.chosen_minutes not in view.rhythm_choices)
        # Id 0, which no rhythm can have: choosing it changes nothing now and
        # leaves whatever interval is already set until Settings changes it.
        self._rhythms.addButton(custom, 0)
        self._choice_layout.addWidget(custom)

        self._rhythms.idToggled.connect(self._on_rhythm)
        self._choices.setVisible(True)

    def _build_autostart(self, view: OnboardingView) -> None:
        self._autostart_yes.setChecked(view.autostart)
        self._autostart_no.setChecked(not view.autostart)
        for button in (self._autostart_yes, self._autostart_no):
            self._choice_layout.addWidget(button)
            button.setVisible(True)
        self._choices.setVisible(True)

    # --- answers -----------------------------------------------------------

    def _on_rhythm(self, minutes: int, checked: bool) -> None:
        if not checked or minutes <= 0:
            return
        try:
            self._flow.choose_rhythm(minutes)
        except InvalidSettings:
            # Unreachable from the preset buttons, which are all values Ocura
            # accepts. Caught rather than trusted because a refused rhythm must
            # never be a dialog that cannot be dismissed.
            return

    def _on_autostart(self, enabled: bool) -> None:
        self._flow.set_autostart(enabled)

    def _on_back(self) -> None:
        self._flow.back()
        self.render(self._flow.view())

    def _on_advance(self) -> None:
        if not self._flow.view().is_last:
            self._flow.next()
            self.render(self._flow.view())
            return
        settings: Settings = self._flow.finish()
        self.completed.emit(settings)
        self.accept()

    def keyPressEvent(self, event) -> None:
        """Escape does not dismiss this.

        Three questions with defaults already chosen, and the application
        behind it is not configured until they are answered. A dialog closed by
        a stray keystroke would leave someone in an Ocura that never introduced
        itself and never will.
        """
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)
