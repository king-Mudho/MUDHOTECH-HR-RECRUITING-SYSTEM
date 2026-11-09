from django.contrib import admin

from .models import Question, Questionnaire, QuestionOption


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ("name", "organisation", "job_version", "is_template", "status", "version")
    list_filter = ("is_template", "status")
    search_fields = ("name",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("key", "questionnaire", "type", "required", "is_knockout", "order")
    list_filter = ("type", "is_knockout")
    search_fields = ("key", "prompt")
    inlines = [QuestionOptionInline]
