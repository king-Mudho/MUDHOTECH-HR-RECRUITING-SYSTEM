from django.contrib import admin

from .models import EmailSuppression, Notification, NotificationTemplate


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ("key", "channel", "locale", "version", "active", "organisation")
    list_filter = ("channel", "active", "locale")
    search_fields = ("key", "subject")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("key", "channel", "status", "recipient_user", "created_at", "sent_at")
    list_filter = ("channel", "status")
    search_fields = ("key", "dedupe_key")
    readonly_fields = ("payload",)


@admin.register(EmailSuppression)
class EmailSuppressionAdmin(admin.ModelAdmin):
    list_display = ("email", "reason", "at")
    list_filter = ("reason",)
    search_fields = ("email",)
