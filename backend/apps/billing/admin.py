from django.contrib import admin

from apps.core.admin import TenantAdminMixin

from .models import Invoice, Payment, Plan, Subscription, UsageCounter


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "price_usd", "price_zwg", "active", "is_public", "order")
    list_editable = ("active", "is_public", "order")


@admin.register(Subscription)
class SubscriptionAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("organisation", "plan", "status", "current_period_end", "grace_until")
    list_filter = ("status", "plan")


@admin.register(UsageCounter)
class UsageCounterAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("organisation", "metric", "period", "value")
    list_filter = ("metric",)


@admin.register(Invoice)
class InvoiceAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("number", "organisation", "currency", "amount", "status", "due_at", "paid_at")
    list_filter = ("status", "currency")
    readonly_fields = ("lines", "snapshot")


@admin.register(Payment)
class PaymentAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("reference", "invoice", "provider", "method", "status", "amount", "paid_at")
    list_filter = ("status", "provider", "method")
    readonly_fields = ("raw",)
