from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import NotificationTemplateViewSet
from .webhooks import SesFeedbackWebhook

router = SimpleRouter()
router.register(
    "hr/notification-templates", NotificationTemplateViewSet, basename="hr-notification-templates"
)

urlpatterns = [
    path("", include(router.urls)),
    path("webhooks/ses/", SesFeedbackWebhook.as_view(), name="webhook-ses"),
]
