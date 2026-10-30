"""Ocura — calm, context-aware break reminders for Windows.

**This is the only place the version number is written.** Everything that has
to know it reads it from here: the wheel metadata through hatchling, the
executable's file properties through the PyInstaller spec, the installer
through a command-line define, the Settings page through an import, and the
release workflow, which refuses to build if the tag it was given disagrees.
Bumping Ocura is therefore one edit, and `tests/unit/test_version.py` fails if
a second copy of the number appears anywhere in the repository.
"""

__version__ = "1.0.1"
