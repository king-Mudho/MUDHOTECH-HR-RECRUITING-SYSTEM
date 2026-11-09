from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import CustomSkillViewSet, QualificationLevelsView, SkillSearchView

router = SimpleRouter()
router.register("custom-skills", CustomSkillViewSet, basename="org-custom-skills")

urlpatterns = [
    path("taxonomy/skills/", SkillSearchView.as_view(), name="taxonomy-skills"),
    path(
        "taxonomy/qualification-levels/",
        QualificationLevelsView.as_view(),
        name="taxonomy-qualification-levels",
    ),
    path("organisations/<uuid:organisation_id>/", include(router.urls)),
]
