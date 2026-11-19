from django.urls import path
from rest_framework.routers import SimpleRouter

from . import console as c
from .views import PlatformOrganisationViewSet

router = SimpleRouter()
router.register(
    "platform/organisations", PlatformOrganisationViewSet, basename="platform-organisations"
)

urlpatterns = [
    path("platform/overview/", c.PlatformOverviewView.as_view(), name="platform-overview"),
    path(
        "platform/organisations/<uuid:organisation_id>/detail/",
        c.PlatformOrgDetailView.as_view(),
        name="platform-organisation-detail",
    ),
    path("platform/users/", c.PlatformUsersView.as_view(), name="platform-users"),
    path("platform/flags/", c.PlatformFlagsView.as_view(), name="platform-flags"),
    path("platform/dead-letters/", c.PlatformDeadLettersView.as_view(), name="platform-dlq"),
    path(
        "platform/dead-letters/<uuid:dead_letter_id>/retry/",
        c.PlatformDeadLetterRetryView.as_view(),
        name="platform-dlq-retry",
    ),
    path(
        "platform/dead-letters/<uuid:dead_letter_id>/resolve/",
        c.PlatformDeadLetterResolveView.as_view(),
        name="platform-dlq-resolve",
    ),
    path("platform/system/", c.PlatformSystemView.as_view(), name="platform-system"),
    path("platform/taxonomy/", c.TaxonomyStatusView.as_view(), name="platform-taxonomy"),
    path(
        "platform/taxonomy/skills/",
        c.TaxonomySkillsView.as_view(),
        name="platform-taxonomy-skills",
    ),
    path(
        "platform/taxonomy/skills/<uuid:skill_id>/",
        c.TaxonomySkillView.as_view(),
        name="platform-taxonomy-skill",
    ),
    path(
        "platform/taxonomy/skills/<uuid:skill_id>/aliases/",
        c.TaxonomySkillAliasesView.as_view(),
        name="platform-taxonomy-skill-aliases",
    ),
    path(
        "platform/taxonomy/aliases/<uuid:alias_id>/",
        c.TaxonomyAliasView.as_view(),
        name="platform-taxonomy-alias",
    ),
    path(
        "platform/taxonomy/relations/",
        c.TaxonomyRelationsView.as_view(),
        name="platform-taxonomy-relations",
    ),
    path(
        "platform/taxonomy/relations/<uuid:relation_id>/",
        c.TaxonomyRelationView.as_view(),
        name="platform-taxonomy-relation",
    ),
    path(
        "platform/taxonomy/qualifications/",
        c.TaxonomyQualificationsView.as_view(),
        name="platform-taxonomy-qualifications",
    ),
    path(
        "platform/taxonomy/qualifications/<uuid:level_id>/aliases/",
        c.TaxonomyQualificationAliasesView.as_view(),
        name="platform-taxonomy-qualification-aliases",
    ),
    path(
        "platform/taxonomy/qualification-aliases/<uuid:alias_id>/",
        c.TaxonomyQualificationAliasView.as_view(),
        name="platform-taxonomy-qualification-alias",
    ),
    *router.urls,
]
