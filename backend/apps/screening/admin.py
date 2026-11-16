from django.contrib import admin

from .models import Evaluation, ScreeningRun


@admin.register(ScreeningRun)
class ScreeningRunAdmin(admin.ModelAdmin):
    list_display = ("id", "organisation", "job", "trigger", "status", "total", "done", "failed")
    list_filter = ("status", "trigger")

    def has_add_permission(self, request: object) -> bool:
        return False


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    """Operational view only: no explanation text (it quotes CVs)."""

    list_display = ("id", "organisation", "version", "status", "band", "coverage", "engine_version")
    list_filter = ("status", "band")
    exclude = ("explanation", "summary")

    def has_add_permission(self, request: object) -> bool:
        return False
