from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QProgressBar

from ocura.ui.app import THEME_KEY, initial_theme
from ocura.ui.main_window import MainWindow
from ocura.ui.motion import FADE_MS, Motion
from ocura.ui.resources import APP_ICON, ICON_SIZES, app_icon
from ocura.ui.theme import DARK, LIGHT

from .test_shell import a_view


def test_the_bundled_icon_loads_from_package_data():
    """Loaded as package data so it survives packaging, not as a repo path."""
    icon = app_icon()
    assert not icon.isNull()
    assert {size.width() for size in icon.availableSizes()} >= set(ICON_SIZES)


def test_the_shipped_icon_is_the_real_one_not_the_generated_fallback():
    from importlib import resources

    from ocura.ui.resources import ASSETS

    assert (resources.files(ASSETS) / APP_ICON).is_file()


def test_the_icon_has_transparency_rather_than_a_black_box():
    icon = app_icon()
    image = icon.pixmap(64, 64).toImage()
    assert image.pixelColor(0, 0).alpha() == 0


def test_the_theme_toggle_switches_and_persists(qtbot, icon, settings):
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)

    window.set_theme_name(DARK.name)
    assert window._theme_button.text() == "Light theme"
    window.set_theme_name(LIGHT.name)
    assert window._theme_button.text() == "Dark theme"

    with qtbot.waitSignal(window.themeToggled, timeout=500):
        window._theme_button.click()


def test_the_toggle_button_lives_in_the_sidebar_not_in_settings(qtbot, icon, settings):
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)

    sidebar = window._theme_button.parent()
    assert sidebar.objectName() == "Sidebar"
    for index in (1, 2):
        page_text = " ".join(
            child.text()
            for child in window._pages.widget(index).findChildren(type(window._theme_button))
        )
        assert "theme" not in page_text.lower()


def test_a_remembered_theme_wins_over_the_system(tmp_path):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue(THEME_KEY, LIGHT.name)
    assert initial_theme(settings) == LIGHT.name


def test_an_unknown_stored_theme_is_ignored(tmp_path, qapp):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    settings.setValue(THEME_KEY, "chartreuse")
    assert initial_theme(settings) in (DARK.name, LIGHT.name)


def test_first_run_follows_the_system_or_falls_back_to_dark(tmp_path, qapp):
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    scheme = qapp.styleHints().colorScheme()

    chosen = initial_theme(settings)
    if scheme == Qt.ColorScheme.Light:
        assert chosen == LIGHT.name
    elif scheme == Qt.ColorScheme.Dark:
        assert chosen == DARK.name
    else:
        assert chosen == DARK.name


def test_reduced_motion_applies_values_immediately(qtbot):
    bar = QProgressBar()
    qtbot.addWidget(bar)
    bar.setRange(0, 1000)
    bar.setValue(0)

    Motion(enabled=False).fill(bar, 400)
    assert bar.value() == 400


def test_motion_glides_towards_the_target_then_stops(qtbot):
    bar = QProgressBar()
    qtbot.addWidget(bar)
    bar.setRange(0, 1000)
    bar.setValue(0)

    Motion(enabled=True).fill(bar, 1000)
    # Mid-flight it is somewhere in between, not already there.
    qtbot.wait(FADE_MS)
    assert 0 < bar.value() < 1000

    qtbot.waitUntil(lambda: bar.value() == 1000, timeout=3000)


def test_a_backwards_jump_is_not_animated(qtbot):
    """A break finishing resets the fill; rewinding it visibly would be motion
    with nothing behind it."""
    bar = QProgressBar()
    qtbot.addWidget(bar)
    bar.setRange(0, 1000)
    bar.setValue(900)

    Motion(enabled=True).fill(bar, 0)
    assert bar.value() == 0


def test_an_unchanged_state_starts_no_animation(qtbot, still):
    """Rendering the same view twice must not move anything."""
    from ocura.ui.views import DashboardView

    still.enabled = True
    dashboard = DashboardView()
    qtbot.addWidget(dashboard)

    view = a_view(progress=0.5)
    dashboard.render(view)
    qtbot.waitUntil(lambda: dashboard._progress.value() == 500, timeout=3000)

    effect_before = dashboard._status.graphicsEffect()
    dashboard.render(view)
    qtbot.wait(FADE_MS // 2)
    # Same headline, so no new fade was created and the fill has nowhere to go.
    assert dashboard._status.graphicsEffect() is effect_before
    assert dashboard._progress.value() == 500


@pytest.mark.parametrize("theme", [DARK, LIGHT])
def test_both_themes_style_the_toggle_button(qtbot, icon, settings, qapp, theme):
    from ocura.ui.theme import stylesheet

    qapp.setStyleSheet(stylesheet(theme))
    window = MainWindow(icon, settings)
    qtbot.addWidget(window)
    window.set_theme_name(theme.name)

    assert window._theme_button.objectName() == "NavButton"
    assert window._theme_button.styleSheet() == ""
