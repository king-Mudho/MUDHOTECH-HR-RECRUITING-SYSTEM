"""Taxonomy: fixtures, versioned loading, autocomplete, resolution, custom skills."""

from __future__ import annotations

import json
import shutil
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.core.exceptions import ConflictError
from apps.organisations.tests.factories import make_org_with_team
from apps.taxonomy import selectors, services
from apps.taxonomy.models import (
    ProfessionalBody,
    QualificationLevel,
    Skill,
    SkillAlias,
    SkillRelation,
    TaxonomyVersion,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def taxonomy() -> services.LoadResult:
    return services.load_taxonomy()


def test_fixture_coverage_meets_spec() -> None:
    doc = json.loads((services.FIXTURE_DIR / "skills.json").read_text(encoding="utf-8"))
    assert len(doc["skills"]) >= 600
    sectors = {s["category"] for s in doc["skills"]}
    assert {
        "software_it",
        "finance",
        "engineering",
        "health",
        "sales_marketing",
        "logistics",
        "education",
        "agriculture",
        "mining",
        "ngo",
    } <= sectors
    quals = json.loads((services.FIXTURE_DIR / "qualifications.json").read_text(encoding="utf-8"))
    codes = {lvl["code"] for lvl in quals["levels"]}
    assert {
        "ZW_OLEVEL",
        "ZW_ALEVEL",
        "ZW_NC",
        "ZW_ND",
        "ZW_HND",
        "BACHELOR",
        "HONOURS",
        "PGDIP",
        "MASTERS",
        "PHD",
    } <= codes
    bodies = {b["code"] for b in quals["professional_bodies"]}
    assert {"ACCA", "CIMA", "ICAZ", "CIPS", "IODZ", "ECZ", "NCZ", "LSZ"} <= bodies


def test_load_is_idempotent_and_versioned(taxonomy: services.LoadResult) -> None:
    assert not taxonomy.skipped and taxonomy.counts["skills"] >= 600
    skills = Skill.objects.count()
    again = services.load_taxonomy()
    assert again.skipped and Skill.objects.count() == skills
    assert TaxonomyVersion.objects.get().version == taxonomy.version
    assert services.current_version() == taxonomy.version
    out = StringIO()
    call_command("load_taxonomy", stdout=out)
    assert "nothing to do" in out.getvalue()


def test_changed_content_same_version_conflicts(taxonomy: Any, tmp_path: Path) -> None:
    for name in ("skills.json", "qualifications.json"):
        shutil.copy(services.FIXTURE_DIR / name, tmp_path / name)
    doc = json.loads((tmp_path / "skills.json").read_text(encoding="utf-8"))
    doc["skills"] = doc["skills"][:-1]  # drop one skill without bumping version
    (tmp_path / "skills.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ConflictError):
        services.load_taxonomy(tmp_path)
    result = services.load_taxonomy(tmp_path, force=True)
    assert not result.skipped
    removed = Skill.objects.get(
        slug__isnull=False,
        canonical_name=json.loads(
            (services.FIXTURE_DIR / "skills.json").read_text(encoding="utf-8")
        )["skills"][-1]["name"],
    )
    assert removed.is_active is False  # deactivated, never deleted


def test_aliases_relations_and_qualifications(taxonomy: Any) -> None:
    assert selectors.resolve_skill("JS").canonical_name == "JavaScript"  # type: ignore[union-attr]
    assert selectors.resolve_skill("postgres").canonical_name == "PostgreSQL"  # type: ignore[union-attr]
    assert selectors.resolve_skill("MS Excel").canonical_name == "Microsoft Excel"  # type: ignore[union-attr]
    assert selectors.resolve_skill("nonexistent skill") is None
    assert selectors.resolve_skill("") is None
    django = Skill.objects.get(canonical_name="Django")
    assert SkillRelation.objects.filter(
        from_skill=django, to_skill__canonical_name="Python", relation="implies"
    ).exists()
    react = Skill.objects.get(canonical_name="React")
    assert SkillRelation.objects.filter(
        from_skill=react, to_skill__canonical_name="JavaScript"
    ).exists()
    hnd = QualificationLevel.objects.get(code="ZW_HND")
    assert hnd.rank > QualificationLevel.objects.get(code="ZW_ND").rank
    assert hnd.aliases.filter(alias="HND").exists()
    assert ProfessionalBody.objects.get(code="ICAZ").designations == [
        "CA(Z)",
        "Chartered Accountant (Zimbabwe)",
    ]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("pyth", "Python"),
        ("javascrpt", "JavaScript"),
        ("js", "JavaScript"),
        ("postgres", "PostgreSQL"),
        ("excel", "Microsoft Excel"),
        ("nursing", "Nursing"),
    ],
)
def test_autocomplete_finds_names_aliases_and_typos(
    taxonomy: Any, query: str, expected: str
) -> None:
    names = [s.canonical_name for s in selectors.search_skills(query, limit=10)]
    assert expected in names, names


def test_autocomplete_api_includes_org_custom_skills_only_for_that_org(taxonomy: Any) -> None:
    team, other = make_org_with_team(), make_org_with_team()
    services.create_custom_skill(
        org=team.org,
        actor=team.hr_manager,
        name="AcmeLedger Pro",
        category="finance",
        aliases=["ALP"],
    )
    mine = APIClient()
    mine.force_login(team.recruiter)
    body = mine.get(
        "/api/v1/taxonomy/skills/", {"search": "AcmeLedger"}, HTTP_X_ORG_ID=str(team.org.pk)
    ).json()
    assert [s["canonical_name"] for s in body][:1] == ["AcmeLedger Pro"] and body[0]["is_custom"]
    theirs = APIClient()
    theirs.force_login(other.recruiter)
    body = theirs.get(
        "/api/v1/taxonomy/skills/", {"search": "AcmeLedger"}, HTTP_X_ORG_ID=str(other.org.pk)
    ).json()
    assert all(s["canonical_name"] != "AcmeLedger Pro" for s in body)
    assert APIClient().get("/api/v1/taxonomy/skills/").status_code in (401, 403)
    assert mine.get("/api/v1/taxonomy/skills/", {"limit": "x"}).status_code == 200


def test_qualification_levels_public(taxonomy: Any) -> None:
    body = APIClient().get("/api/v1/taxonomy/qualification-levels/").json()
    ranks = [lvl["rank"] for lvl in body]
    assert ranks == sorted(ranks) and any(lvl["code"] == "ZW_OLEVEL" for lvl in body)


def test_custom_skill_crud_permissions(taxonomy: Any) -> None:
    team = make_org_with_team()
    url = f"/api/v1/organisations/{team.org.pk}/custom-skills/"
    hr = APIClient()
    hr.force_login(team.hr_manager)
    created = hr.post(
        url,
        {"canonical_name": "SAP Ariba Local", "category": "logistics", "aliases": ["Ariba ZW"]},
        format="json",
    )
    assert created.status_code == 201
    assert (
        hr.post(
            url, {"canonical_name": "SAP Ariba Local", "category": "logistics"}, format="json"
        ).status_code
        == 409
    )
    recruiter = APIClient()
    recruiter.force_login(team.recruiter)
    assert recruiter.get(url).json()["count"] == 1
    assert (
        recruiter.post(
            url, {"canonical_name": "X", "category": "general"}, format="json"
        ).status_code
        == 403
    )
    assert hr.delete(f"{url}{created.json()['id']}/").status_code == 204
    assert hr.get(url).json()["count"] == 0
    assert SkillAlias.objects.filter(alias="Ariba ZW").exists()
