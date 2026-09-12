"""Raw Win32 calls, one function per question. The only module that imports ctypes.

Everything here is a plain function with no state, so the detectors above can be
tested by substituting an ordinary callable. Nothing in this file is exercised by
the test suite: it is the boundary where mocking stops being meaningful.

Polling rather than window messages is deliberate. Lock and unlock notifications
(WTSRegisterSessionNotification, WM_WTSSESSION_CHANGE) need an HWND and a message
pump, which would drag a UI dependency into the infrastructure layer and invert
the direction of the whole architecture. A one-second poll costs nothing at this
scale and keeps P1 free of Qt.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)

SPI_GETSCREENSAVERRUNNING = 0x0072
DESKTOP_SWITCHDESKTOP = 0x0100

QUNS_NOT_PRESENT = 1
QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4
QUNS_ACCEPTS_NOTIFICATIONS = 5
QUNS_QUIET_TIME = 6
QUNS_APP = 7

#: States in which Windows itself suppresses notifications. Ocura defers to that
#: judgement rather than inventing a competing one.
_DO_NOT_DISTURB = frozenset(
    {
        QUNS_BUSY,
        QUNS_RUNNING_D3D_FULL_SCREEN,
        QUNS_PRESENTATION_MODE,
        QUNS_QUIET_TIME,
        QUNS_APP,
    }
)


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))


_user32.GetLastInputInfo.argtypes = (ctypes.POINTER(_LASTINPUTINFO),)
_user32.GetLastInputInfo.restype = wintypes.BOOL
_kernel32.GetTickCount64.restype = ctypes.c_ulonglong
_user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_user32.OpenInputDesktop.restype = wintypes.HANDLE
_user32.CloseDesktop.argtypes = (wintypes.HANDLE,)
_user32.CloseDesktop.restype = wintypes.BOOL
_user32.SystemParametersInfoW.argtypes = (
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    wintypes.UINT,
)
_user32.SystemParametersInfoW.restype = wintypes.BOOL
_shell32.SHQueryUserNotificationState.argtypes = (ctypes.POINTER(ctypes.c_int),)
_shell32.SHQueryUserNotificationState.restype = ctypes.HRESULT


def idle_seconds() -> float:
    """Seconds since the last keyboard or mouse input, session-wide."""
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    # dwTime is a 32-bit tick count and wraps every 49.7 days, so the current
    # tick has to be truncated to 32 bits and the difference taken modulo 2**32.
    # Subtracting it from a raw GetTickCount64 would report decades of idleness
    # on any machine up longer than that.
    now = _kernel32.GetTickCount64() & 0xFFFFFFFF
    return ((now - info.dwTime) & 0xFFFFFFFF) / 1000.0


def is_locked() -> bool:
    """True when the input desktop cannot be opened, which is what locking does."""
    desktop = _user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not desktop:
        return True
    _user32.CloseDesktop(desktop)
    return False


def is_screensaver_running() -> bool:
    running = wintypes.BOOL()
    if not _user32.SystemParametersInfoW(SPI_GETSCREENSAVERRUNNING, 0, ctypes.byref(running), 0):
        return False
    return bool(running.value)


def user_notification_state() -> int:
    """Windows' own answer to "is this a good moment to show something".

    Preferred over comparing the foreground window rectangle to the monitor
    rectangle, which was the first attempt here and was wrong: a *maximized*
    window overhangs its monitor by the invisible resize border, so every
    maximized window read as fullscreen and every break would have been deferred
    forever. This API distinguishes maximized from fullscreen, and additionally
    knows about presentation mode and Focus Assist, which no rectangle can.
    """
    state = ctypes.c_int()
    try:
        _shell32.SHQueryUserNotificationState(ctypes.byref(state))
    except OSError:
        return QUNS_ACCEPTS_NOTIFICATIONS
    return state.value


def is_presenting() -> bool:
    """True when a fullscreen app, presentation mode or Focus Assist is active."""
    return user_notification_state() in _DO_NOT_DISTURB
