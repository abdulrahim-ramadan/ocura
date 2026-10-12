"""Qt picks the plural form by each language's own rule, from the shipped .qm.

`tests/unit/test_catalogues.py` proves the forms are in the catalogues. This
proves they come back out for the right numbers once compiled — that lrelease
read the language's plural rule, that the port passes the count through, and
that the six Arabic categories land where Arabic puts them.
"""

from __future__ import annotations

import pytest

from ocura.application.i18n import duration_words, translate
from ocura.ui.language import Language


@pytest.fixture
def language(qapp):
    handle = Language(qapp)
    was = qapp.layoutDirection()
    yield handle
    handle.apply("en")
    qapp.setLayoutDirection(was)


def seconds(n: int) -> str:
    return translate("Units", "%n seconds", None, n)


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "0 ثانية"),
        (1, "ثانية واحدة"),
        (2, "ثانيتين"),
        (3, "3 ثوانٍ"),
        (10, "10 ثوانٍ"),
        (11, "11 ثانية"),
        (99, "99 ثانية"),
        (100, "100 ثانية"),
        # The rule is on the last two digits, not on the size of the number.
        (103, "103 ثوانٍ"),
        (111, "111 ثانية"),
    ],
)
def test_arabic_picks_each_of_its_six_forms(language, n, expected):
    language.apply("ar")
    assert seconds(n) == expected


def test_the_break_minimum_reads_as_arabic_writes_it(language):
    """Five seconds is the shortest break Ocura accepts, and it was the case
    that read wrong: "5 ثانية" where Arabic says "5 ثوانٍ"."""
    language.apply("ar")
    assert duration_words(5) == "5 ثوانٍ"
    assert duration_words(120) == "دقيقتين"


@pytest.mark.parametrize(
    ("code", "one", "many"),
    [("de", "1 Sekunde", "2 Sekunden"), ("en", "1 second", "2 seconds")],
)
def test_german_and_english_have_a_singular_and_a_plural(language, code, one, many):
    language.apply(code)
    assert seconds(1) == one
    assert seconds(2) == many
    assert seconds(0) == many.replace("2", "0")


def test_english_says_once_rather_than_one_times(language):
    language.apply("en")
    note = translate(
        "Statistics",
        "Ocura held a break back %n times this week rather than interrupting, and "
        "waited for a better moment. This is why.",
        None,
        1,
    )
    assert "once this week" in note
