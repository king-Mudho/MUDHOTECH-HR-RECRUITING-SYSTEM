from rest_framework.routers import SimpleRouter

from .views import PlatformOrganisationViewSet

router = SimpleRouter()
router.register(
    "platform/organisations", PlatformOrganisationViewSet, basename="platform-organisations"
)

urlpatterns = router.urls
