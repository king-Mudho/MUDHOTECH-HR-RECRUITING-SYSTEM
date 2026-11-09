from django.contrib import admin

from .models import (
    ProfessionalBody,
    QualificationAlias,
    QualificationLevel,
    Skill,
    SkillAlias,
    SkillRelation,
    TaxonomyVersion,
)


class SkillAliasInline(admin.TabularInline):
    model = SkillAlias
    extra = 0


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("canonical_name", "category", "organisation", "is_active", "taxonomy_version")
    list_filter = ("category", "is_active")
    search_fields = ("canonical_name", "aliases__alias")
    inlines = [SkillAliasInline]
    exclude = ("embedding",)


class QualificationAliasInline(admin.TabularInline):
    model = QualificationAlias
    extra = 0


@admin.register(QualificationLevel)
class QualificationLevelAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "rank", "framework")
    inlines = [QualificationAliasInline]


admin.site.register(SkillRelation)
admin.site.register(ProfessionalBody)
admin.site.register(TaxonomyVersion)
