"""Date and date-range parsing for CVs (docs/05 §6.1, EC-DOC-17/19).

Recognised: ``Jan 2020``, ``January 2020``, ``Jan. 2020``, ``Jan '20``, ``01/2020``,
``2020-01``, ``2020/01``, ``03/04/2019`` (day first, as written in Zimbabwe), ``2020``, ``'20``,
current markers (Present, Current, To date, Date, Now, Ongoing, Till date; French présent,
aujourd'hui, en cours), separators (hyphen and dashes, ``to`` ``till`` ``until`` ``through``
``à``), the short
form ``2019-21`` and ``Since/From 2020`` (open-ended, current). Year-only dates get
``precision=year``. Ranges that end before they start, start in the future, or end more than six
months ahead are returned with an anomaly (and no usable range): they are never counted as
experience and become clarification suggestions, not penalties.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_engine.contracts import DatePrecision, DateRange, PartialDate

YearMonth = tuple[int, int]
FUTURE_TOLERANCE_MONTHS = 6
MIN_YEAR = 1950

MONTHS = {
    "jan": 1,
    "january": 1,
    "janv": 1,
    "janvier": 1,
    "feb": 2,
    "february": 2,
    "fev": 2,
    "fevr": 2,
    "fevrier": 2,
    "février": 2,
    "févr": 2,
    "mar": 3,
    "march": 3,
    "mars": 3,
    "apr": 4,
    "april": 4,
    "avr": 4,
    "avril": 4,
    "may": 5,
    "mai": 5,
    "jun": 6,
    "june": 6,
    "juin": 6,
    "jul": 7,
    "july": 7,
    "juil": 7,
    "juillet": 7,
    "aug": 8,
    "august": 8,
    "aout": 8,
    "août": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "septembre": 9,
    "oct": 10,
    "october": 10,
    "octobre": 10,
    "nov": 11,
    "november": 11,
    "novembre": 11,
    "dec": 12,
    "december": 12,
    "dece": 12,
    "décembre": 12,
    "decembre": 12,
    "déc": 12,
}
_MONTH_NAMES = "|".join(sorted(MONTHS, key=len, reverse=True))

CURRENT = (
    r"present|current(?:ly)?|to\s+date|till\s+date|todate|up\s+to\s+date|date|now|ongoing|"
    r"présent|present|aujourd'hui|ce\s+jour|en\s+cours"
)

# one date; named groups are prefixed so a range can hold two of them
_DATE = (
    r"(?:(?P<{p}mname>" + _MONTH_NAMES + r")\.?,?\s*(?P<{p}myear>(?:19|20)\d{{2}}|'\d{{2}})"
    r"|(?P<{p}day>[0-3]?\d)[/.](?P<{p}dmonth>[01]?\d)[/.](?P<{p}dyear>(?:19|20)\d{{2}})"
    r"|(?P<{p}nmonth>[01]?\d)[/.](?P<{p}nyear>(?:19|20)\d{{2}})"
    r"|(?P<{p}iyear>(?:19|20)\d{{2}})[-/.](?P<{p}imonth>[01]\d)(?![\d/.-]\d)"
    r"|(?P<{p}year>(?:19|20)\d{{2}})"
    r"|(?P<{p}syear>'\d{{2}}))"
)
# hyphen, en dash, em dash (dashes are normalised upstream; kept for direct callers)
_SEP = r"\s*(?:-|\u2013|\u2014|to|till|until|through|thru|à|au)\s*"
_RANGE = re.compile(
    r"(?<![\w/])"
    + _DATE.format(p="s_")
    + _SEP
    + r"(?:(?P<current>"
    + CURRENT
    + r")\b|"
    + _DATE.format(p="e_")
    + r"|(?P<short>\d{2})(?!\d))"
    + r"(?![\w/])",
    re.IGNORECASE,
)
_SINCE = re.compile(
    r"\b(?:since|from|depuis)\s+" + _DATE.format(p="s_") + r"(?![\w/])", re.IGNORECASE
)


@dataclass(frozen=True)
class DateMatch:
    char_start: int
    char_end: int
    text: str
    range: DateRange | None  # None when the dates are unusable (see anomaly)
    anomaly: str | None = None  # reversed | future_start | future_end | impossible


def _year(raw: str, today: YearMonth) -> int:
    if raw.startswith("'"):
        short = int(raw[1:])
        return 2000 + short if short <= today[0] % 100 + 1 else 1900 + short
    return int(raw)


def _date(m: re.Match[str], p: str, today: YearMonth) -> PartialDate | None:
    g = m.groupdict()
    try:
        if g.get(f"{p}mname"):
            month = MONTHS[g[f"{p}mname"].lower()]
            return PartialDate(year=_year(g[f"{p}myear"], today), month=month)
        if g.get(f"{p}dyear"):
            day, month = int(g[f"{p}day"]), int(g[f"{p}dmonth"])
            if not 1 <= day <= 31:
                return None
            return PartialDate(year=int(g[f"{p}dyear"]), month=month)
        if g.get(f"{p}nyear"):
            return PartialDate(year=int(g[f"{p}nyear"]), month=int(g[f"{p}nmonth"]))
        if g.get(f"{p}iyear"):
            return PartialDate(year=int(g[f"{p}iyear"]), month=int(g[f"{p}imonth"]))
        if g.get(f"{p}year"):
            return PartialDate(year=int(g[f"{p}year"]), precision=DatePrecision.YEAR)
        if g.get(f"{p}syear"):
            return PartialDate(year=_year(g[f"{p}syear"], today), precision=DatePrecision.YEAR)
    except ValueError:  # month 13 etc. (pydantic ValidationError is a ValueError)
        return None
    return None


def month_index(d: PartialDate, *, end: bool = False) -> int:
    """Months since year 0; year-only dates start in January and end in December."""
    return d.ordinal(end=end)


def _check(start: PartialDate, end: PartialDate | None, today: YearMonth) -> str | None:
    now = today[0] * 12 + (today[1] - 1)
    if start.year < MIN_YEAR or (end is not None and end.year < MIN_YEAR):
        return "impossible"
    if end is not None and month_index(end, end=True) < month_index(start):
        return "reversed"
    if month_index(start) > now + 1 and start.precision == DatePrecision.MONTH:
        return "future_start"
    if start.precision == DatePrecision.YEAR and start.year > today[0]:
        return "future_start"
    if end is not None and month_index(end) > now + FUTURE_TOLERANCE_MONTHS:
        return "future_end"
    return None


def _build(
    m: re.Match[str],
    start: PartialDate | None,
    end: PartialDate | None,
    current: bool,
    today: YearMonth,
) -> DateMatch | None:
    if start is None:
        return None
    text = m.group(0).strip()
    anomaly = _check(start, end, today)
    usable = None
    if anomaly is None:
        usable = DateRange(start=start, end=None if current else end, is_current=current)
    return DateMatch(m.start(), m.start() + len(m.group(0).rstrip()), text, usable, anomaly)


def find_date_ranges(text: str, today: YearMonth) -> list[DateMatch]:
    """All date ranges in ``text`` in order; overlapping matches are resolved left to right."""
    found: list[DateMatch] = []
    taken: list[tuple[int, int]] = []
    for m in _RANGE.finditer(text):
        start = _date(m, "s_", today)
        current = bool(m.group("current"))
        end: PartialDate | None = None
        if m.group("short") and start is not None:
            century = start.year - start.year % 100
            year = century + int(m.group("short"))
            if year < start.year:
                year += 100
            end = PartialDate(year=year, precision=DatePrecision.YEAR) if year <= 2100 else None
            if end is None:
                continue
        elif not current:
            end = _date(m, "e_", today)
            if end is None:
                continue
        match = _build(m, start, end, current, today)
        if match is not None:
            found.append(match)
            taken.append((m.start(), m.end()))
    for m in _SINCE.finditer(text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        match = _build(m, _date(m, "s_", today), None, True, today)
        if match is not None:
            found.append(match)
    return sorted(found, key=lambda d: d.char_start)


def parse_single_date(text: str, today: YearMonth) -> PartialDate | None:
    """One date such as a graduation year or certificate issue date."""
    m = re.search(r"(?<![\w/])" + _DATE.format(p="s_") + r"(?![\w/])", text, re.IGNORECASE)
    return _date(m, "s_", today) if m else None
