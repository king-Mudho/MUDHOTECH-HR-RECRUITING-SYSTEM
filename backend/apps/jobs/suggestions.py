"""AI-assist stub for vacancy authoring (P03-T08).

Deterministic heuristics only (no LLM until Phase 07): skills named in the advert text are matched
against the taxonomy (canonical names + aliases, 1-4 word n-grams). Output is a list of
*suggestions*: nothing is saved, every item must be accepted by a person, and suggested criteria
default to ``preferred`` (deciding what is essential is an HR judgement that needs a
justification). Guarded by the ``jobs.ai_suggestions`` flag (default off) and the organisation's
``ai_enabled`` policy.
"""

from __future__ import annotations

import re
from typing import Any

from apps.core import flags
from apps.core.exceptions import DomainError
from apps.organisations.models import OrganisationPolicy
from apps.taxonomy.models import SkillAlias
from apps.taxonomy.selectors import visible_skills

from .models import Job
from .search import plain_text

FLAG = "jobs.ai_suggestions"
MAX_NGRAM = 4
MAX_CRITERIA = 12
WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]*")


class SuggestionsDisabledError(DomainError):
    code = "feature_disabled"
    status_code = 403
    default_message = "AI suggestions are not enabled for your organisation."


def enabled_for(job: Job) -> bool:
    policy = OrganisationPolicy.objects.filter(organisation_id=job.organisation_id).first()
    return flags.is_enabled(FLAG, job.organisation) and bool(policy and policy.ai_enabled)


def _vocabulary(org: Any) -> dict[str, Any]:
    vocab: dict[str, Any] = {}
    skills = {s.pk: s for s in visible_skills(org).only("id", "canonical_name", "organisation_id")}
    for s in skills.values():
        vocab.setdefault(s.canonical_name.lower(), s)
    aliases = SkillAlias.objects.filter(skill_id__in=skills.keys()).values_list("alias", "skill_id")
    for alias, skill_id in aliases:
        vocab.setdefault(alias.lower(), skills[skill_id])
    return vocab


def _tokens(text: str) -> list[str]:
    return [t.rstrip(".-") for t in WORD_RE.findall(text.lower())]


def extract_skills(text: str, org: Any = None) -> list[Any]:
    """Skills mentioned in ``text``, in order of first mention, longest match first."""
    vocab = _vocabulary(org)
    tokens = _tokens(text)
    found: dict[Any, Any] = {}
    i = 0
    while i < len(tokens):
        for n in range(min(MAX_NGRAM, len(tokens) - i), 0, -1):
            phrase = " ".join(tokens[i : i + n])
            skill = vocab.get(phrase)
            if skill is not None and len(phrase) > 1:
                found.setdefault(skill.pk, skill)
                i += n
                break
        else:
            i += 1
    return list(found.values())


def suggest(job: Job) -> dict[str, Any]:
    if not enabled_for(job):
        raise SuggestionsDisabledError()
    version = job.current_version
    text = " ".join(
        [
            job.title,
            version.summary if version else "",
            plain_text(version.responsibilities_html) if version else "",
            plain_text(version.requirements_html) if version else "",
        ]
    )
    existing = {c.skill_id for c in version.criteria.all() if c.skill_id} if version else set()
    skills = [s for s in extract_skills(text, job.organisation) if s.pk not in existing]
    criteria = [
        {
            "type": "skill",
            "importance": "preferred",
            "title": s.canonical_name,
            "skill_id": str(s.pk),
            "rubric_category": "technical",
            "evidence_guidance": f"Look for projects or roles where {s.canonical_name} was used.",
            "source": "heuristic",
            "reason": "Mentioned in the advert text.",
        }
        for s in skills[:MAX_CRITERIA]
    ]
    questions: list[dict[str, Any]] = []
    if skills:
        top = skills[0]
        questions.append(
            {
                "key": f"years-{re.sub(r'[^a-z0-9]+', '-', top.canonical_name.lower()).strip('-')}"[
                    :60
                ],
                "type": "number",
                "prompt": f"How many years of hands-on experience do you have with "
                f"{top.canonical_name}?",
                "config": {"min": 0, "max": 50, "unit": "years"},
                "scoring": {"mode": "none"},
                "source": "heuristic",
            }
        )
    questions.append(
        {
            "key": "notice-period",
            "type": "availability",
            "prompt": "What is your notice period (in weeks)?",
            "config": {"min": 0, "max": 26, "unit": "weeks"},
            "scoring": {"mode": "none"},
            "source": "heuristic",
        }
    )
    return {
        "engine": "heuristic-v1",
        "requires_acceptance": True,
        "criteria": criteria,
        "questions": questions,
    }
