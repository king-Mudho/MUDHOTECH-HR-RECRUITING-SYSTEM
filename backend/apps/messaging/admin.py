from django.contrib import admin

from .models import ClarificationRequest, MessageThread


@admin.register(ClarificationRequest)
class ClarificationRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "application", "status", "due_at", "answered_at")
    list_filter = ("status",)
    readonly_fields = ("questions", "answers")


@admin.register(MessageThread)
class MessageThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "application", "status", "created_at")
