from django.contrib import admin

from apps.core.admin import TenantAdminMixin

from .models import Job, JobAssignment, JobCriterion, JobEvent, JobVersion, Rubric


class JobVersionInline(admin.TabularInline):
    model = JobVersion
    extra = 0
    fields = ("number", "status", "approved_at")
    readonly_fields = fields
    show_change_link = True


@admin.register(Job)
class JobAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("title", "organisation", "status", "visibility", "closes_at", "published_at")
    list_filter = ("status", "visibility", "employment_type")
    search_fields = ("title", "slug", "reference_code")
    readonly_fields = ("search_vector", "lock_version")
    inlines = [JobVersionInline]


@admin.register(JobVersion)
class JobVersionAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("job", "number", "status", "approved_at")


@admin.register(JobCriterion)
class JobCriterionAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("title", "job_version", "type", "importance", "rubric_category")


@admin.register(Rubric)
class RubricAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("job_version", "version", "status", "total_weight")


@admin.register(JobAssignment)
class JobAssignmentAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("job", "membership", "role_on_job")


@admin.register(JobEvent)
class JobEventAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("job", "action", "from_status", "to_status", "actor", "created_at")
