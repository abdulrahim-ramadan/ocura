from __future__ import annotations


class OcuraError(Exception):
    pass


class ConfigurationError(OcuraError):
    """A schedule that cannot be honoured, e.g. a break longer than the focus block."""


class TransitionError(OcuraError):
    """A command that the current timer state cannot serve."""
