# ruff: noqa: RUF001 - en dashes are test input
"""Dates and experience totals (P06-T06): EC-DOC-17..21."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_engine.contracts import DatePrecision, DateRange, EmploymentKind, PartialDate, SectionKind
from ai_engine.extraction.dates import find_date_ranges, parse_single_date
from ai_engine.extraction.extract import extract_document
from ai_engine.normalisation.experience import Role, classify_employment, interval, merge, summarise

TODAY = (2026, 10)
CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic_cvs"
K = EmploymentKind


def one(text: str) -> DateRange:
    matches = find_date_ranges(text, TODAY)
    assert len(matches) == 1, (text, matches)
    assert matches[0].anomaly is None and matches[0].range is not None, matches[0]
    return matches[0].range


def ym(d: PartialDate | None) -> tuple[int, int | None, str] | None:
    return None if d is None else (d.year, d.month, d.precision.value)


@pytest.mark.parametrize(
    ("text", "start", "end", "current"),
    [
        ("Jan 2020 - Mar 2022", (2020, 1, "month"), (2022, 3, "month"), False),
        ("January 2020 to December 2021", (2020, 1, "month"), (2021, 12, "month"), False),
        ("Sept. 2019 – Present", (2019, 9, "month"), None, True),
        ("01/2020 - 06/2021", (2020, 1, "month"), (2021, 6, "month"), False),
        ("2020-01 - current", (2020, 1, "month"), None, True),
        ("2018/03 till 2019/11", (2018, 3, "month"), (2019, 11, "month"), False),
        ("03/04/2019 - 30/06/2020", (2019, 4, "month"), (2020, 6, "month"), False),  # day first
        ("2015 - 2018", (2015, None, "year"), (2018, None, "year"), False),
        ("2019–21", (2019, None, "year"), (2021, None, "year"), False),
        ("Jan '20 - Dec '21", (2020, 1, "month"), (2021, 12, "month"), False),
        ("May 2024 - now", (2024, 5, "month"), None, True),
        ("2021 - To date", (2021, None, "year"), None, True),
        ("Since 2020", (2020, None, "year"), None, True),
        ("From March 2023", (2023, 3, "month"), None, True),
        ("09/2025 - to date", (2025, 9, "month"), None, True),
        ("janvier 2021 - présent", (2021, 1, "month"), None, True),
        ("2022 à 2024", (2022, None, "year"), (2024, None, "year"), False),
    ],
)
def test_date_formats(
    text: str,
    start: tuple[int, int | None, str],
    end: tuple[int, int | None, str] | None,
    current: bool,
) -> None:
    rng = one(f"Software Developer | Econet, Harare | {text}")
    assert ym(rng.start) == start and ym(rng.end) == end and rng.is_current is current


def test_offsets_point_at_the_dates() -> None:
    text = "Accountant | Delta | Feb 2019 - Jan 2021\nClerk | OK Zimbabwe | 2016 - 2018"
    matches = find_date_ranges(text, TODAY)
    assert [text[m.char_start : m.char_end] for m in matches] == [
        "Feb 2019 - Jan 2021",
        "2016 - 2018",
    ]


@pytest.mark.parametrize(
    ("text", "anomaly"),
    [
        ("Mar 2022 - Jan 2020", "reversed"),
        ("2021 - 2019", "reversed"),
        ("Jan 2028 - Present", "future_start"),
        ("2029 - 2030", "future_start"),
        ("Jan 2024 - Dec 2027", "future_end"),
        ("1910 - 1912", "impossible"),
    ],
)
def test_anomalies_are_flagged_and_unusable(text: str, anomaly: str) -> None:
    (match,) = find_date_ranges(text, TODAY)
    assert match.anomaly == anomaly and match.range is None


def test_non_dates_and_single_dates() -> None:
    assert find_date_ranges("Phone +263 77 000 1234, 13/2020 - 14/2021", TODAY) == []
    assert find_date_ranges("ZIMSEC O Level, 6 subjects, 2014", TODAY) == []
    assert ym(parse_single_date("BSc Honours, UZ, 2020", TODAY)) == (2020, None, "year")
    assert ym(parse_single_date("Issued June 2023", TODAY)) == (2023, 6, "month")
    assert parse_single_date("no date here", TODAY) is None
    near_future = find_date_ranges("Jan 2026 - Feb 2027", TODAY)[0]  # within 6 months: allowed
    assert near_future.anomaly is None


# ------------------------------------------------------------------------ experience
@pytest.mark.parametrize(
    ("texts", "section", "kind", "explicit"),
    [
        (("Industrial Attachment Student", "ZESA"), None, K.ATTACHMENT, True),
        (("Work-Related Learning", "NetOne"), None, K.ATTACHMENT, True),
        (("IT Intern", "Econet"), None, K.INTERNSHIP, True),
        (("Volunteer Nurse", "Red Cross"), None, K.VOLUNTEER, True),
        (("Part-time Data Analyst (weekends)", "Freelance"), None, K.PART_TIME, True),
        (("Web Developer", "Freelance"), None, K.SELF_EMPLOYED, True),
        (("Accountant (fixed-term contract)", "ZIMRA"), None, K.CONTRACT, True),
        (("HR Consultant", "Self"), None, K.CONTRACT, True),
        (("Software Developer", "Cassava"), None, K.FULL_TIME, False),
        (("Trainee", "Delta"), SectionKind.ATTACHMENT, K.ATTACHMENT, False),
    ],
)
def test_employment_kind(
    texts: tuple[str, ...], section: SectionKind | None, kind: EmploymentKind, explicit: bool
) -> None:
    assert classify_employment(*texts, section=section) == (kind, explicit)


def r(start: str, end: str | None, kind: EmploymentKind = K.FULL_TIME) -> Role:
    def d(s: str) -> PartialDate:
        if len(s) == 4:
            return PartialDate(year=int(s), precision=DatePrecision.YEAR)
        return PartialDate(year=int(s[:4]), month=int(s[5:]))

    if end is None:
        return Role(DateRange(start=d(start), is_current=True), kind)
    return Role(DateRange(start=d(start), end=d(end)), kind)


def test_overlaps_count_once_and_kinds_are_separate() -> None:
    summary = summarise(
        [
            r("2020-01", "2022-01"),  # 24
            r("2021-01", "2023-01"),  # overlaps 12 -> +12
            r("2019-01", "2019-09", K.ATTACHMENT),
            r("2025-01", "2025-07", K.VOLUNTEER),
            r("2023-01", "2023-07", K.PART_TIME),  # 6 uncovered -> 3
        ],
        TODAY,
    )
    assert summary.total_months == 36 + 3
    assert summary.months_by_kind[K.ATTACHMENT] == 8
    assert summary.months_by_kind[K.VOLUNTEER] == 6
    assert summary.months_by_kind[K.FULL_TIME] == 36
    assert summary.gaps == []  # part-time does not close gaps in the counted timeline either way
    weighted = summarise([r("2023-01", "2023-07", K.PART_TIME)], TODAY, part_time_weight=1.0)
    assert weighted.total_months == 6
    counted = summarise(
        [r("2019-01", "2019-09", K.ATTACHMENT)],
        TODAY,
        counted=frozenset({K.FULL_TIME, K.ATTACHMENT}),
    )
    assert counted.total_months == 8


def test_current_year_only_and_gaps() -> None:
    assert interval(r("2026-01", None).dates, TODAY) == (2026 * 12, 2026 * 12 + 9)
    year_only = summarise([r("2018", "2019")], TODAY)
    assert year_only.total_months == 23  # Jan 2018 .. Dec 2019, end-exclusive
    this_year = summarise([r("2025", "2026")], TODAY)
    assert this_year.total_months == 21  # capped at today
    gapped = summarise([r("2015-01", "2016-01"), r("2018-01", "2019-01")], TODAY)
    assert gapped.gaps == [((2016, 1), (2018, 1))]
    assert gapped.total_months == 24  # gaps are reported, never subtracted or scored
    undated = summarise(
        [Role(DateRange()), Role(DateRange(start=PartialDate(year=2020, month=1)))], TODAY
    )
    assert undated.undated_roles == 2 and undated.total_months == 0
    assert merge([(5, 8), (1, 3), (3, 4)]) == [(1, 4), (5, 8)]


@pytest.mark.skipif(not CORPUS.exists(), reason="synthetic corpus missing")
def test_corpus_dates_and_totals() -> None:
    data = json.loads((CORPUS / "labels.json").read_text(encoding="utf-8"))
    today = tuple(int(x) for x in data["reference_month"].split("-"))
    assert today == TODAY

    def parse(value: str | None) -> PartialDate | None:
        return None if value is None else PartialDate(year=int(value[:4]), month=int(value[5:]))

    problems = []
    for cv in data["cvs"]:
        roles = [
            Role(
                DateRange(start=parse(j["start"]), end=parse(j["end"]), is_current=j["current"]),
                EmploymentKind(j["kind"]),
            )
            for j in cv["experience"]
        ]
        if summarise(roles, TODAY).total_months != cv["total_experience_months"]:
            problems.append((cv["file"], "total"))
        if cv["parse_expected"] != "ok" or cv["needs_ocr"]:
            continue
        text = extract_document((CORPUS / cv["file"]).read_bytes(), document_id="d").document
        assert text is not None
        found = sorted(
            (
                (m.range.start, m.range.end, m.range.is_current)
                for m in find_date_ranges(text.pages[0].text, TODAY)
                if m.range is not None and m.range.start is not None
            ),
            key=str,
        )
        want = sorted(
            ((parse(j["start"]), parse(j["end"]), j["current"]) for j in cv["experience"]), key=str
        )
        if found != want:
            problems.append((cv["file"], "dates"))
    assert problems == []
