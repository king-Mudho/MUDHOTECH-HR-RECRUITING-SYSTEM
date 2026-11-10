from django.contrib import admin

from .models import CandidateProfile


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "headline", "city", "profile_completeness", "updated_at")
    search_fields = ("user__email", "headline")
    raw_id_fields = ("user",)
