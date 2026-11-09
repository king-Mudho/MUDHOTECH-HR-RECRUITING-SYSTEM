"""Prohibited-question linter (FR-M08-06, non-negotiable principle 7).

Screening questions must not ask about protected characteristics: age, religion, tribe/ethnicity,
marital or family status, pregnancy, HIV/health status, disability, political affiliation, national
ID, photos/appearance. The linter flags them with an explanation; an HR manager may record a
documented, lawful job-related exception (``protected_exception_reason``, audited) - otherwise the
question blocks publishing.

Pure Python (no Django): unit-testable and reusable by the AI suggestion stub.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# topic -> (explanation, patterns). Patterns are matched case-insensitively on word boundaries.
TOPICS: dict[str, tuple[str, list[str]]] = {
    "age": (
        "Questions about age or date of birth can lead to age discrimination. Ask about the "
        "job requirement instead (e.g. 'Are you legally permitted to work in Zimbabwe?').",
        [
            r"\bage\b",
            r"\bhow old\b",
            r"\bdate of birth\b",
            r"\bd\.?o\.?b\b",
            r"\bborn in\b",
            r"\byear of birth\b",
            r"\bbirth ?date\b",
        ],
    ),
    "religion": (
        "Religion and church membership are protected characteristics and must not be screened.",
        [
            r"\breligio\w*",
            r"\bchurch\w*",
            r"\bdenomination\b",
            r"\bmosque\b",
            r"\bfaith\b",
            r"\bpray\w*",
            r"\bchristian\b",
            r"\bmuslim\b",
            r"\bapostolic\b",
            r"\bpastor\b",
        ],
    ),
    "tribe_ethnicity": (
        "Tribe, totem, ethnicity, race or home area must not be screened.",
        [
            r"\btrib(e|al)\w*",
            r"\btotem\w*",
            r"\bmutupo\b",
            r"\bethnic\w*",
            r"\brace\b",
            r"\bracial\b",
            r"\bmother tongue\b",
            r"\bhome (area|village|district)\b",
            r"\bkumusha\b",
            r"\bclan\b",
        ],
    ),
    "marital_family": (
        "Marital status, spouse and children are protected and irrelevant to job ability.",
        [
            r"\bmarital\b",
            r"\bmarried\b",
            r"\bsingle\b(?! sign)",
            r"\bdivorc\w*",
            r"\bwidow\w*",
            r"\bspouse\b",
            r"\bhusband\b",
            r"\bwife\b",
            r"\bchildren\b",
            r"\bkids\b",
            r"\bdependants?\b",
            r"\bdependents?\b",
            r"\bfamily plans?\b",
        ],
    ),
    "pregnancy": (
        "Pregnancy and plans to have children must never be asked about.",
        [
            r"\bpregnan\w*",
            r"\bmaternity\b",
            r"\bexpecting a (baby|child)\b",
            r"\bplan(ning)? to have (a )?(baby|child|children)\b",
        ],
    ),
    "health_hiv": (
        "HIV status and medical history are confidential health information. Ask only whether "
        "the candidate can perform the essential duties, with or without reasonable adjustment.",
        [
            r"\bhiv\b",
            r"\baids\b",
            r"\bart\b(?= treatment)",
            r"\bmedical (history|condition)s?\b",
            r"\billness(es)?\b",
            r"\bsick leave history\b",
            r"\bchronic\b",
            r"\bdisease\b",
            r"\bhealth status\b",
            r"\bmental (health|illness)\b",
        ],
    ),
    "disability": (
        "Disability must not be screened; reasonable-adjustment needs are handled separately.",
        [r"\bdisab\w*", r"\bhandicap\w*", r"\bimpair\w*", r"\bwheelchair\b"],
    ),
    "political": (
        "Political opinion and party membership are protected characteristics.",
        [
            r"\bpolitic\w*",
            r"\bparty (member|card|affiliation)\w*",
            r"\bzanu\b",
            r"\bzanu[- ]?pf\b",
            r"\bmdc\b",
            r"\bccc\b",
            r"\bcitizens coalition\b",
            r"\bvot(e|ed|ing) for\b",
            r"\bwar veteran\b",
        ],
    ),
    "gender_sex": (
        "Gender and sex must not be used to screen applicants.",
        [r"\bgender\b", r"\bsex\b", r"\bmale or female\b", r"\bsexual orientation\b"],
    ),
    "national_id": (
        "National ID numbers are not needed to assess suitability and are excessive data "
        "(data minimisation, CDPA). Collect them only after an offer, if required.",
        [
            r"\bnational id\b",
            r"\bid (number|no\.?)\b",
            r"\bnational registration\b",
            r"\bpassport number\b",
            r"\bbirth certificate\b",
        ],
    ),
    "appearance": (
        "Photos, height, weight or appearance must not be requested for screening.",
        [
            r"\bphoto(graph)?s?\b",
            r"\bselfie\b",
            r"\bheight\b",
            r"\bweight\b",
            r"\bappearance\b",
            r"\bcomplexion\b",
        ],
    ),
}

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    topic: [re.compile(p, re.IGNORECASE) for p in patterns]
    for topic, (_, patterns) in TOPICS.items()
}


@dataclass(frozen=True)
class LintWarning:
    topic: str
    matched: str
    explanation: str
    field: str  # prompt | help_text | option

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def lint_text(text: str, field: str = "prompt") -> list[LintWarning]:
    warnings: list[LintWarning] = []
    if not text:
        return warnings
    for topic, patterns in _COMPILED.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                warnings.append(
                    LintWarning(
                        topic=topic,
                        matched=match.group(0),
                        explanation=TOPICS[topic][0],
                        field=field,
                    )
                )
                break  # one warning per topic per field
    return warnings


def lint_question(
    prompt: str, help_text: str = "", options: list[str] | None = None
) -> list[LintWarning]:
    """All protected-topic warnings for a question (prompt, help text and option labels)."""
    found = lint_text(prompt, "prompt") + lint_text(help_text, "help_text")
    for label in options or []:
        found += lint_text(label, "option")
    unique: dict[str, LintWarning] = {}
    for w in found:
        unique.setdefault(w.topic, w)
    return list(unique.values())
