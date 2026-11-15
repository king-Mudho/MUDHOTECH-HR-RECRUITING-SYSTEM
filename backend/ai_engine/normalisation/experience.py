"""Experience normalisation: employment kind and total months (docs/05 §6.1, EC-DOC-18/20/21).

Month arithmetic is end-exclusive (Jan→Mar = 2 months) so consecutive roles that share a month
are not double counted; a current role runs to ``today``. Total relevant experience is the
**union** of counted roles, so overlapping jobs count once. Part-time months not already covered
by a full-time role count at ``part_time_weight`` (0.5 by default, configurable). Attachments,
internships and volunteer work are totalled separately and always shown - never discarded,
never part of the default total. Gaps are computed for the timeline only; nothing scores them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise

from ai_engine.contracts import DatePrecision, DateRange, EmploymentKind, SectionKind

YearMonth = tuple[int, int]
K = EmploymentKind

DEFAULT_COUNTED = frozenset({K.FULL_TIME, K.CONTRACT, K.SELF_EMPLOYED, K.UNKNOWN})
SEPARATE = frozenset({K.ATTACHMENT, K.INTERNSHIP, K.VOLUNTEER})

_KIND_PATTERNS: list[tuple[EmploymentKind, re.Pattern[str]]] = [
    (
        K.ATTACHMENT,
        re.compile(
            r"industrial attachment|attachment student|attachee|work[- ]related learning|\bWRL\b",
            re.IGNORECASE,
        ),
    ),
    (K.INTERNSHIP, re.compile(r"\bintern(ship)?s?\b|\bgraduate trainee\b|\bstagiaire\b", re.I)),
    (K.VOLUNTEER, re.compile(r"\bvolunt(eer|ary|eering)\b|\bpro bono\b|\bbénévole\b", re.I)),
    (K.PART_TIME, re.compile(r"\bpart[- ]time\b|\bweekends?\b|\bhalf[- ]day\b", re.I)),
    (
        K.SELF_EMPLOYED,
        re.compile(
            r"\bfreelanc(e|er|ing)\b|\bself[- ]employed\b|\bsole (trader|proprietor)\b|"
            r"\bown business\b|\bfounder\b|\bco-founder\b",
            re.I,
        ),
    ),
    (
        K.CONTRACT,
        re.compile(
            r"\bcontract(or|ual)?\b|\bconsultan(t|cy)\b|\bfixed[- ]term\b|\btemporary\b|\blocum\b",
            re.I,
        ),
    ),
    (K.FULL_TIME, re.compile(r"\bfull[- ]time\b|\bpermanent\b", re.I)),
]


def classify_employment(
    *texts: str, section: SectionKind | None = None
) -> tuple[EmploymentKind, bool]:
    """(kind, explicit). Title, employer and the role's lines are searched in that order.

    Without a cue, a role in an experience section is taken as full-time (``explicit=False``);
    roles in an attachment/internship section are attachments.
    """
    joined = " \n ".join(t for t in texts if t)
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(joined):
            return kind, True
    if section == SectionKind.ATTACHMENT:
        return K.ATTACHMENT, False
    return K.FULL_TIME, False


@dataclass(frozen=True)
class Role:
    """What the total needs from an experience claim."""

    dates: DateRange
    kind: EmploymentKind = K.FULL_TIME


@dataclass
class ExperienceSummary:
    total_months: int
    months_by_kind: dict[EmploymentKind, int]
    gaps: list[tuple[YearMonth, YearMonth]] = field(default_factory=list)  # never scored
    undated_roles: int = 0


def _index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def interval(dates: DateRange, today: YearMonth) -> tuple[int, int] | None:
    """[start, end) month indexes, or None when the role has no usable start."""
    if dates.start is None:
        return None
    start = dates.start
    s = _index(start.year, start.month or 1)
    now = _index(*today)
    if dates.is_current or dates.end is None:
        if not dates.is_current:
            return None  # an end we could not read: do not guess
        e = now
    else:
        end = dates.end
        e = _index(end.year, end.month or 12)
        if end.precision == DatePrecision.YEAR and end.year == today[0]:
            e = min(e, now)  # "2019 - 2026" in 2026 cannot run past today
    e = min(e, now)
    return (s, e) if e > s else None


def merge(intervals: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def covered(intervals: Iterable[tuple[int, int]]) -> int:
    return sum(e - s for s, e in merge(intervals))


def _ym(index: int) -> YearMonth:
    return (index // 12, index % 12 + 1)


def summarise(
    roles: Iterable[Role],
    today: YearMonth,
    *,
    counted: frozenset[EmploymentKind] = DEFAULT_COUNTED,
    part_time_weight: float = 0.5,
) -> ExperienceSummary:
    by_kind: dict[EmploymentKind, list[tuple[int, int]]] = {}
    undated = 0
    for role in roles:
        span = interval(role.dates, today)
        if span is None:
            undated += 1
            continue
        by_kind.setdefault(role.kind, []).append(span)
    main = [span for kind, spans in by_kind.items() if kind in counted for span in spans]
    main_merged = merge(main)
    total = float(covered(main_merged))
    if K.PART_TIME not in counted and part_time_weight > 0:
        extra = covered(main_merged + by_kind.get(K.PART_TIME, [])) - covered(main_merged)
        total += extra * part_time_weight
    gaps = [
        (_ym(a_end), _ym(b_start))
        for (_, a_end), (b_start, _) in pairwise(main_merged)
        if b_start - a_end >= 1
    ]
    return ExperienceSummary(
        total_months=int(total),
        months_by_kind={kind: covered(spans) for kind, spans in by_kind.items()},
        gaps=gaps,
        undated_roles=undated,
    )
