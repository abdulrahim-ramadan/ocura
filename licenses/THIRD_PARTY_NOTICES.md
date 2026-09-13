# Third-party notices

Ocura itself is source-available and **not** open source — see `LICENSE`, which
is included beside this file. The components below are separate works with their
own terms, redistributed with Ocura, and nothing in Ocura's licence restricts
your rights under theirs.

## Qt for Python (PySide6) and Shiboken6 — LGPL v3

- PySide6 6.11.2, Shiboken6 6.11.2
- Copyright (C) The Qt Company Ltd. and other contributors
- https://www.qt.io/qt-for-python
- Licensed under the **GNU Lesser General Public License version 3**, included
  as `LGPL-3.0.txt`. LGPL v3 incorporates the GNU General Public License v3 by
  reference, included as `GPL-3.0.txt`.

## Qt — LGPL v3

- Qt 6.11.2, bundled with PySide6 as the DLLs in `_internal/`
- Copyright (C) The Qt Company Ltd. and other contributors
- https://www.qt.io
- Licensed under the **GNU Lesser General Public License version 3**, as above.

### Your right to replace the Qt libraries

The LGPL requires that you be able to run Ocura against your own build of Qt.
This distribution is deliberately arranged so you can:

- Ocura is shipped as a **directory**, not a single-file executable. A one-file
  build unpacks itself to a temporary directory on every launch, leaving nothing
  durable to replace, and would not satisfy this condition.
- The Qt libraries are ordinary, separate `.dll` files under `_internal/`. You
  may replace them with a compatible build of Qt 6 of your own and run the
  result.
- No Qt library is statically linked into `Ocura.exe`, and none is modified.

If a replacement build of Qt is binary-incompatible, Ocura will fail to start;
that is a compatibility limit of the Qt version, not a restriction imposed here.

## Python

- CPython 3.13, bundled as `python3*.dll` and the standard library
- Copyright (C) 2001-2026 Python Software Foundation
- https://www.python.org
- Licensed under the **PSF License Agreement**, a permissive licence:
  https://docs.python.org/3/license.html

## Obtaining the source

Ocura's own source is published at
https://github.com/abdulrahim-ramadan/ocura under the terms in `LICENSE`.
Source for Qt, PySide6 and CPython is available from the upstream projects
linked above.
