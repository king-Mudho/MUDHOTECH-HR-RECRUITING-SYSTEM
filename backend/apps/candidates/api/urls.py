from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    CertificationViewSet,
    EducationViewSet,
    ExperienceViewSet,
    LanguageViewSet,
    ProfileView,
    ResumeDeleteView,
    ResumeListView,
    ResumeSetDefaultView,
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
    path("candidate/resumes/", ResumeListView.as_view(), name="candidate-resumes"),
    path(
        "candidate/resumes/<uuid:document_id>/set-default/",
        ResumeSetDefaultView.as_view(),
        name="candidate-resume-default",
    ),
    path(
        "candidate/resumes/<uuid:document_id>/", ResumeDeleteView.as_view(), name="candidate-resume"
    ),
]
