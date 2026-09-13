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
_wtsapi32 = ctypes.WinDLL("wtsapi32", use_last_error=True)

SPI_GETSCREENSAVERRUNNING = 0x0072
DESKTOP_SWITCHDESKTOP = 0x0100

WTS_CURRENT_SESSION = 0xFFFFFFFF
WTS_SESSION_INFO_EX = 25
#: Windows 8 and later. Windows 7 and Server 2008 R2 invert these two, which is
#: irrelevant here: Ocura requires Windows 10 or newer.
WTS_SESSIONSTATE_LOCK = 0
WTS_SESSIONSTATE_UNLOCK = 1

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


class _WTSINFOEX_LEVEL1(ctypes.Structure):
    """Declared in full: the trailing fields set the struct's 8-byte alignment,
    and truncating them silently shifts SessionFlags to the wrong offset."""

    _fields_ = (
        ("SessionId", wintypes.DWORD),
        ("SessionState", ctypes.c_int),
        ("SessionFlags", ctypes.c_long),
        ("WinStationName", wintypes.WCHAR * 33),
        ("UserName", wintypes.WCHAR * 21),
        ("DomainName", wintypes.WCHAR * 18),
        ("LogonTime", ctypes.c_longlong),
        ("ConnectTime", ctypes.c_longlong),
        ("DisconnectTime", ctypes.c_longlong),
        ("LastInputTime", ctypes.c_longlong),
        ("CurrentTime", ctypes.c_longlong),
        ("IncomingBytes", wintypes.DWORD),
        ("OutgoingBytes", wintypes.DWORD),
        ("IncomingFrames", wintypes.DWORD),
        ("OutgoingFrames", wintypes.DWORD),
        ("IncomingCompressedBytes", wintypes.DWORD),
        ("OutgoingCompressedBytes", wintypes.DWORD),
    )


class _WTSINFOEX(ctypes.Structure):
    _fields_ = (("Level", wintypes.DWORD), ("Data", _WTSINFOEX_LEVEL1))


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
_wtsapi32.WTSQuerySessionInformationW.argtypes = (
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(wintypes.DWORD),
)
_wtsapi32.WTSQuerySessionInformationW.restype = wintypes.BOOL
_wtsapi32.WTSFreeMemory.argtypes = (ctypes.c_void_p,)
_wtsapi32.WTSFreeMemory.restype = None


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


def locked_via_wts() -> bool | None:
    """Authoritative lock state, or None if the session could not be queried."""
    buffer = ctypes.c_void_p()
    returned = wintypes.DWORD()
    ok = _wtsapi32.WTSQuerySessionInformationW(
        None,
        WTS_CURRENT_SESSION,
        WTS_SESSION_INFO_EX,
        ctypes.byref(buffer),
        ctypes.byref(returned),
    )
    if not ok or not buffer:
        return None
    try:
        info = ctypes.cast(buffer, ctypes.POINTER(_WTSINFOEX)).contents
        flags = info.Data.SessionFlags
    finally:
        _wtsapi32.WTSFreeMemory(buffer)

    if flags == WTS_SESSIONSTATE_LOCK:
        return True
    if flags == WTS_SESSIONSTATE_UNLOCK:
        return False
    return None


def locked_via_input_desktop() -> bool:
    """Fallback only. Reports the *secure desktop*, which is not the same thing.

    OpenInputDesktop does not fail when the session locks; it fails once the
    secure desktop actually becomes the input desktop, which typically waits for
    the display to sleep. Measured against WTS on a real lock: WTS saw it at
    00:38, this saw it at 01:05, and both saw the unlock at 01:08 — so a 30
    second absence was measured as 3 seconds. Anything shorter than
    break_duration is refused by satisfy_break, so the rest credit was silently
    starved and no break was ever discharged. Keep this only for the case where
    the WTS query itself fails.
    """
    desktop = _user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not desktop:
        return True
    _user32.CloseDesktop(desktop)
    return False


def is_locked() -> bool:
    locked = locked_via_wts()
    if locked is None:
        return locked_via_input_desktop()
    return locked


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
