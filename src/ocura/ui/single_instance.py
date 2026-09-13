"""One engine per machine.

Two Ocura processes would tick two independent BreakTimers against the same
person, double-count every break and disagree in the tray. A second launch
therefore hands its request to the first and exits.

QLocalServer over a named pipe rather than a lock file: a lock file left behind
by a crash blocks every future launch, whereas a pipe dies with its process.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "ocura-single-instance"
_HANDSHAKE = b"raise"
_TIMEOUT_MS = 500


class SingleInstance(QObject):
    """Owns the pipe when it is the first instance."""

    raiseRequested = Signal()

    def __init__(self, name: str = SERVER_NAME, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._server: QLocalServer | None = None

    def claim(self) -> bool:
        """True if this process is the only instance and now owns the pipe."""
        if self._notify_existing():
            return False

        server = QLocalServer(self)
        # A previous crash can leave the name taken with nothing behind it; the
        # probe above already proved nobody is listening.
        QLocalServer.removeServer(self._name)
        if not server.listen(self._name):
            # Losing the race is still a second instance, so step aside quietly.
            return False

        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def close(self) -> None:
        if self._server is not None:
            self._server.close()
            self._server = None

    def _notify_existing(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self._name)
        if not socket.waitForConnected(_TIMEOUT_MS):
            return False
        socket.write(_HANDSHAKE)
        socket.waitForBytesWritten(_TIMEOUT_MS)
        socket.disconnectFromServer()
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        connection = self._server.nextPendingConnection()
        if connection is None:
            return
        connection.readyRead.connect(lambda: connection.readAll())
        connection.disconnected.connect(connection.deleteLater)
        self.raiseRequested.emit()
