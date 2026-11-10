from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    CertificationViewSet,
    EducationViewSet,
    ExperienceViewSet,
    LanguageViewSet,
    ProfileView,
    SkillViewSet,
)

router = SimpleRouter()
router.register("experiences", ExperienceViewSet, basename="candidate-experiences")
router.register("educations", EducationViewSet, basename="candidate-educations")
router.register("certifications", CertificationViewSet, basename="candidate-certifications")
router.register("skills", SkillViewSet, basename="candidate-skills")
router.register("languages", LanguageViewSet, basename="candidate-languages")

urlpatterns = [
    path("candidate/profile/", ProfileView.as_view(), name="candidate-profile"),
    path("candidate/profile/", include(router.urls)),
]
