from django.contrib import admin

from app_users import models
from bots.admin_links import open_in_new_tab, list_related_html_url
from bots.models import SavedRun


# Register your models here.


@admin.register(models.AppUser)
class AppUserAdmin(admin.ModelAdmin):
    list_display = [
        "uid",
        "display_name",
        "email",
        "phone_number",
        "balance",
        "is_paying",
        "is_anonymous",
        "is_disabled",
        "created_at",
        "upgraded_from_anonymous_at",
    ]
    search_fields = [
        "uid",
        "display_name",
        "email",
        "phone_number",
        "stripe_customer_id",
    ]
    list_filter = [
        "is_anonymous",
        "is_disabled",
        "is_paying",
        "created_at",
        "upgraded_from_anonymous_at",
    ]
    readonly_fields = [
        "created_at",
        "upgraded_from_anonymous_at",
        "view_transactions",
        "open_in_firebase",
        "open_in_stripe",
    ]

    def open_in_firebase(self, user: models.AppUser):
        path = f"users/{user.uid}"
        return open_in_new_tab(
            f"https://console.firebase.google.com/u/0/project/dara-c1b52/firestore/data/{path}",
            label=path,
        )

    open_in_firebase.short_description = "Open in Firebase"

    def open_in_stripe(self, user: models.AppUser):
        if not user.stripe_customer_id:
            # Try to find the customer ID.
            user.search_stripe_customer()
        if not user.stripe_customer_id:
            # If we still don't have a customer ID, return None.
            raise AttributeError("No Stripe customer ID found.")
        return open_in_new_tab(
            f"https://dashboard.stripe.com/customers/{user.stripe_customer_id}",
            label=user.stripe_customer_id,
        )

    open_in_stripe.short_description = "Open in Stripe"

    @admin.display(description="View transactions")
    def view_transactions(self, user: models.AppUser):
        return list_related_html_url(user.transactions, show_add=False)


class SavedRunInline(admin.StackedInline):
    model = SavedRun
    extra = 0
    fields = readonly_fields = [
        "open_in_gooey",
        "price",
        "created_at",
        "updated_at",
        "run_time",
    ]
    show_change_link = True

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class HasSavedRunFilter(admin.SimpleListFilter):
    title = "Has saved run"
    parameter_name = "has_saved_run"

    def lookups(self, request, model_admin):
        return (
            ("1", "Yes"),
            ("0", "No"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset
        return queryset.exclude(saved_runs__isnull=bool(int(value))).distinct()


@admin.register(models.AppUserTransaction)
class AppUserTransactionAdmin(admin.ModelAdmin):
    autocomplete_fields = ["user"]
    list_display = [
        "invoice_id",
        "user",
        "amount",
        "created_at",
        "end_balance",
    ]
    readonly_fields = ["created_at"]
    list_filter = ["created_at", HasSavedRunFilter]
    inlines = [SavedRunInline]
    ordering = ["-created_at"]
