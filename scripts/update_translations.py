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

**Counted messages are finished here, not by lupdate.** A source containing
`%n` is counted (see `ocura.application.i18n`), but lupdate's Python parser
only marks `numerus` for `self.tr(text, "", n)`, and on a re-run it strips a
flag it did not set, keeps the first form and drops the rest (both measured).
So the forms are read out of each catalogue before lupdate touches it, and put
back after: every `%n` message is flagged and gets exactly as many forms as
its language has plural categories, the old ones where they existed and empty,
unfinished ones where they did not. Linguist then shows all six Arabic forms
to fill in, and lrelease compiles them.

The edit is done on lupdate's text, one message block at a time, rather than
through an XML library: re-serialising would re-escape every quote in the
file and turn each update into a diff of the whole catalogue.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "src" / "ocura"
CATALOGUES = SOURCES / "ui" / "i18n"

#: English is the source language, and its catalogue holds the counted messages
#: only: a `%n` source is written in the plural and its singular has to live
#: somewhere. Every other sentence is already English in the code, and a
#: second copy would be free to disagree with the first.
LANGUAGES = ("ar", "de", "en")
SOURCE_LANGUAGE = "en"

#: Plural categories per language, in Qt's order. Arabic: zero, one, two, few
#: (3-10), many (11-99), other (100 and up). Measured against lrelease and
#: QTranslator rather than taken from a table, and asserted again at runtime
#: by tests/gui/test_plurals.py.
NUMERUS_FORMS = {"ar": 6, "de": 2, "en": 2}

COUNTED = "%n"

CONTEXT = re.compile(r"<context>\s*<name>(.*?)</name>(.*?)</context>\n?", re.DOTALL)
MESSAGE = re.compile(r'( *)<message(?: numerus="yes")?>(.*?)</message>\n?', re.DOTALL)
TRANSLATION = re.compile(r"<translation[^>]*?(?:/>|>.*?</translation>)", re.DOTALL)
FORM = re.compile(r"<numerusform>(.*?)</numerusform>", re.DOTALL)


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


def language_of(catalogue: Path) -> str:
    return catalogue.stem.removeprefix("ocura_")


def _key(context: str, body: str) -> tuple[str, str, str]:
    source = re.search(r"<source>(.*?)</source>", body, re.DOTALL)
    comment = re.search(r"<comment>(.*?)</comment>", body, re.DOTALL)
    return context, source.group(1) if source else "", comment.group(1) if comment else ""


def counted_forms(catalogue: Path) -> dict[tuple[str, str, str], list[str]]:
    """The plural forms already written, by (context, source, comment)."""
    if not catalogue.exists():
        return {}
    found = {}
    for context in CONTEXT.finditer(catalogue.read_text(encoding="utf-8")):
        for message in MESSAGE.finditer(context.group(2)):
            forms = FORM.findall(message.group(2))
            if forms:
                found[_key(context.group(1), message.group(2))] = forms
    return found


def finish_counted(catalogue: Path, kept: dict[tuple[str, str, str], list[str]]) -> None:
    """Flag every `%n` message, restore its forms, and for English drop the rest."""
    language = language_of(catalogue)
    wanted = NUMERUS_FORMS[language]
    text = catalogue.read_text(encoding="utf-8")

    def message(match: re.Match, context: str) -> str:
        indent, body = match.group(1), match.group(2)
        key = _key(context, body)
        if COUNTED not in key[1]:
            return "" if language == SOURCE_LANGUAGE else match.group(0)
        forms = (kept.get(key, []) + [""] * wanted)[:wanted]
        state = "" if all(forms) else ' type="unfinished"'
        lines = "".join(f"\n{indent * 3}<numerusform>{form}</numerusform>" for form in forms)
        translation = f"<translation{state}>{lines}\n{indent * 2}</translation>"
        body = TRANSLATION.sub(lambda _: translation, body, count=1)
        return f'{indent}<message numerus="yes">{body}</message>\n'

    def context(match: re.Match) -> str:
        name = match.group(1)
        body = MESSAGE.sub(lambda m: message(m, name), match.group(2))
        if "<message" not in body:
            return ""
        return f"<context>\n    <name>{name}</name>{body}</context>\n"

    catalogue.write_text(CONTEXT.sub(context, text), encoding="utf-8")


def counted_problems(catalogue: Path) -> list[str]:
    """Counted messages that are not flagged or lack a form, and, in English,
    anything that is not a counted message at all."""
    language = language_of(catalogue)
    wanted = NUMERUS_FORMS[language]
    problems = []
    for context in ElementTree.parse(catalogue).getroot():
        for message in context.findall("message"):
            source = message.findtext("source") or ""
            if COUNTED not in source:
                if language == SOURCE_LANGUAGE:
                    problems.append(f"{catalogue.name}: not a counted message {source!r}")
                continue
            forms = [form.text or "" for form in message.iter("numerusform")]
            if message.get("numerus") != "yes" or len(forms) != wanted or not all(forms):
                written = sum(1 for form in forms if form)
                problems.append(
                    f"{catalogue.name}: {written} of {wanted} plural forms for {source!r}"
                )
    return problems


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
            expected = wanted
            if language_of(catalogue) == SOURCE_LANGUAGE:
                expected = {entry for entry in wanted if COUNTED in entry[1]}
            problems.extend(counted_problems(catalogue))
            for context, source in sorted(expected - have):
                problems.append(f"{catalogue.name}: missing [{context}] {source!r}")
            for context, source in sorted(have - expected):
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

    kept = {catalogue: counted_forms(catalogue) for catalogue in catalogues}
    print(extract_into([str(catalogue) for catalogue in catalogues]).strip())
    for catalogue in catalogues:
        finish_counted(catalogue, kept[catalogue])
    for catalogue in catalogues:
        print(run([tool("pyside6-lrelease"), str(catalogue)]).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
