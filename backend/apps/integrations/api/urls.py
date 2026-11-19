from django.urls import path

from . import views as v

urlpatterns = [
    path("hr/integrations/", v.IntegrationsView.as_view(), name="hr-integrations"),
    path(
        "hr/integrations/<uuid:connection_id>/",
        v.IntegrationView.as_view(),
        name="hr-integration",
    ),
    path(
        "hr/integrations/<uuid:connection_id>/rotate/",
        v.IntegrationRotateView.as_view(),
        name="hr-integration-rotate",
    ),
    path(
        "hr/integrations/<uuid:connection_id>/test/",
        v.IntegrationTestView.as_view(),
        name="hr-integration-test",
    ),
    path("hr/webhooks/", v.WebhooksView.as_view(), name="hr-webhooks"),
    path("hr/webhooks/<uuid:endpoint_id>/", v.WebhookEndpointView.as_view(), name="hr-webhook"),
    path(
        "hr/webhooks/<uuid:endpoint_id>/rotate/",
        v.WebhookRotateView.as_view(),
        name="hr-webhook-rotate",
    ),
    path(
        "hr/webhooks/deliveries/<uuid:delivery_id>/replay/",
        v.WebhookReplayView.as_view(),
        name="hr-webhook-replay",
    ),
    path("hr/api-keys/", v.ApiKeysView.as_view(), name="hr-api-keys"),
    path("hr/api-keys/<uuid:key_id>/", v.ApiKeyView.as_view(), name="hr-api-key"),
    path("public-api/jobs/", v.PublicApiJobsView.as_view(), name="public-api-jobs"),
    path(
        "public-api/applications/",
        v.PublicApiApplicationsView.as_view(),
        name="public-api-applications",
    ),
    path("feeds/<slug:org_slug>/jobs.xml", v.JobsFeedXmlView.as_view(), name="feeds-jobs-xml"),
    path("feeds/<slug:org_slug>/jobs.json", v.JobsFeedJsonView.as_view(), name="feeds-jobs-json"),
    path(
        "candidate/messaging-preferences/",
        v.CandidateMessagingView.as_view(),
        name="candidate-messaging-preferences",
    ),
    path("integrations/sms/receipt/", v.SmsReceiptView.as_view(), name="integrations-sms-receipt"),
    path("integrations/sms/inbound/", v.SmsInboundView.as_view(), name="integrations-sms-inbound"),
    path(
        "integrations/whatsapp/webhook/",
        v.WhatsAppWebhookView.as_view(),
        name="integrations-whatsapp-webhook",
    ),
]
