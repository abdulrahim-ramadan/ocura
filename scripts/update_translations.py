"""Re-extract the catalogues and compile them. Windows, with the dev extras.

    python scripts/update_translations.py            # extract and compile
    python scripts/update_translations.py --check    # say what would change

**Every Python file under src/ocura is scanned, not only the UI.** Most of
Ocura's language lives in the application layer — the rules about it are a
product decision and `tests/unit/` asserts them without a display — and two of
the sentences a person can be shown are raised from `infrastructure`. lupdate
reads the source rather than running it, so a file left off this list is a file
whose strings silently never reach a translator.

What lupdate recognises here is a bare `translate("Context", "text")` call and
`QT_TRANSLATE_NOOP`, both of which `ocura.application.i18n` provides without
importing Qt. The context has to be a literal at the call site: a module
constant holding the context name extracts nothing at all.

After running this, open the .ts files in Qt Linguist (`pyside6-linguist`),
translate what is new, and run it again to compile. A .qm is what ships; the
.ts is the source of record and is the file a translator is sent.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "src" / "ocura"
CATALOGUES = SOURCES / "ui" / "i18n"

#: English is the source language and has no catalogue: the strings in the code
#: are already English, and translating English to English would be a second
#: copy of every sentence, free to disagree with the first.
LANGUAGES = ("ar", "de")


def tool(name: str) -> str:
    """The Qt tool beside the interpreter running this, not one on PATH.

    A second Qt on PATH — a system install, another venv — compiles against a
    different version of the format, and the failure surfaces much later as a
    catalogue that loads and translates nothing.
    """
    executable = Path(sys.executable).parent / name
    return str(executable)


def python_files() -> list[str]:
    return [str(path) for path in sorted(SOURCES.rglob("*.py")) if "__pycache__" not in path.parts]


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{command[0]} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr


def extract_into(targets: list[str]) -> str:
    # -no-obsolete: a string that no longer exists in the source is dropped
    # rather than kept as <vanished>. The .ts files are in git, which is a
    # better record of what a sentence used to say than a comment in the
    # catalogue itself.
    return run([tool("pyside6-lupdate"), *python_files(), "-ts", *targets, "-no-obsolete"])


def messages(catalogue: Path) -> set[tuple[str, str]]:
    """Every (context, source) in a .ts file.

    The comparison a check has to make, rather than the bytes: lupdate writes
    each `<location>` relative to the .ts file it is writing, so a catalogue
    extracted into a temporary directory differs from an identical one in the
    tree on every line of it.
    """
    tree = ElementTree.parse(catalogue)
    return {
        (context.findtext("name") or "", message.findtext("source") or "")
        for context in tree.getroot()
        for message in context.findall("message")
    }


def unfinished(catalogue: Path) -> list[str]:
    """Sources with no translation yet. A .qm simply leaves these out, so they
    reach the screen as English in a language that is not English."""
    tree = ElementTree.parse(catalogue)
    return [
        message.findtext("source") or ""
        for context in tree.getroot()
        for message in context.findall("message")
        if (message.find("translation") is not None)
        and message.find("translation").get("type") == "unfinished"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report, do not write")
    arguments = parser.parse_args()

    catalogues = [CATALOGUES / f"ocura_{language}.ts" for language in LANGUAGES]

    if arguments.check:
        # Extracted into copies, so a check never edits the files it checks.
        with tempfile.TemporaryDirectory() as scratch:
            fresh = Path(scratch) / "fresh.ts"
            print(extract_into([str(fresh)]).strip())
            wanted = messages(fresh)

        problems: list[str] = []
        for catalogue in catalogues:
            have = messages(catalogue)
            for context, source in sorted(wanted - have):
                problems.append(f"{catalogue.name}: missing [{context}] {source!r}")
            for context, source in sorted(have - wanted):
                problems.append(f"{catalogue.name}: no longer in the source [{context}] {source!r}")
            for source in unfinished(catalogue):
                problems.append(f"{catalogue.name}: untranslated {source!r}")

        for problem in problems:
            print(problem)
        if problems:
            print("run this without --check, then translate what is new")
            return 1
        print(f"{len(wanted)} strings, all present and translated in {len(catalogues)} catalogues")
        return 0

    print(extract_into([str(catalogue) for catalogue in catalogues]).strip())
    for catalogue in catalogues:
        print(run([tool("pyside6-lrelease"), str(catalogue)]).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
