from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .inbox import InboxListView, MarkAllReadView, MarkReadView, UnreadCountView
from .views import NotificationTemplateViewSet
from .webhooks import SesFeedbackWebhook

router = SimpleRouter()
router.register(
    "hr/notification-templates", NotificationTemplateViewSet, basename="hr-notification-templates"
)

urlpatterns = [
    path("", include(router.urls)),
    path("notifications/", InboxListView.as_view(), name="notifications"),
    path("notifications/unread-count/", UnreadCountView.as_view(), name="notifications-unread"),
    path("notifications/read-all/", MarkAllReadView.as_view(), name="notifications-read-all"),
    path(
        "notifications/<uuid:notification_id>/read/",
        MarkReadView.as_view(),
        name="notifications-read",
    ),
    path("webhooks/ses/", SesFeedbackWebhook.as_view(), name="webhook-ses"),
]
