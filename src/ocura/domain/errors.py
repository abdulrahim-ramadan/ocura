from __future__ import annotations


class OcuraError(Exception):
    pass


class ConfigurationError(OcuraError):
    """A schedule that cannot be honoured, e.g. a break longer than the focus block."""


class TransitionError(OcuraError):
    """A command that the current timer state cannot serve."""


class InsufficientRestError(OcuraError):
    """Rest was reported, but too little of it to discharge an owed break.

    Distinct from TransitionError: the transition itself is legal, the evidence
    behind it is not.
    """
