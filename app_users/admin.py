from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.db.models import Sum

from app_users import models
from bots.admin_links import open_in_new_tab, list_related_html_url
from bots.models import SavedRun
from usage_costs.models import UsageCost


# Register your models here.


@admin.register(models.AppUser)
class AppUserAdmin(admin.ModelAdmin):
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "uid",
                    ("email", "phone_number"),
                    "balance",
                    "subscription",
                    "stripe_customer_id",
                    "total_payments",
                    "total_charged",
                    "total_usage_cost",
                    "is_disabled",
                    "is_anonymous",
                    "is_paying",
                    "disable_safety_checker",
                    "disable_rate_limits",
                    ("user_runs", "view_transactions"),
                    "created_at",
                    "upgraded_from_anonymous_at",
                    ("open_in_firebase", "open_in_stripe"),
                    "low_balance_email_sent_at",
                ],
            },
        ),
        (
            "Profile Options",
            {
                "fields": [
                    "handle",
                    "display_name",
                    "bio",
                    ("company", "github_username"),
                    "website_url",
                    "banner_url",
                    "photo_url",
                ]
            },
        ),
    ]
    list_display = [
        "uid",
        "handle",
        "subscription",
        "display_name",
        "email",
        "phone_number",
        "balance",
        "is_paying",
        "created_at",
    ]
    search_fields = [
        "uid",
        "display_name",
        "email",
        "phone_number",
        "stripe_customer_id",
        "handle__name",
    ]
    list_filter = [
        "is_anonymous",
        "is_disabled",
        "is_paying",
        "created_at",
        "upgraded_from_anonymous_at",
    ]
    readonly_fields = [
        "total_payments",
        "total_charged",
        "total_usage_cost",
        "created_at",
        "upgraded_from_anonymous_at",
        "user_runs",
        "view_transactions",
        "open_in_firebase",
        "open_in_stripe",
        "low_balance_email_sent_at",
    ]
    autocomplete_fields = ["handle", "subscription"]

    @admin.display(description="User Runs")
    def user_runs(self, user: models.AppUser):
        return list_related_html_url(
            SavedRun.objects.filter(uid=user.uid),
            query_param="uid",
            instance_id=user.uid,
            show_add=False,
        )

    @admin.display(description="Total Payments")
    def total_payments(self, user: models.AppUser):
        return "$" + str(
            (
                user.transactions.aggregate(Sum("charged_amount"))[
                    "charged_amount__sum"
                ]
                or 0
            )
            / 100
        )

    @admin.display(description="Total Charged")
    def total_charged(self, user: models.AppUser):
        credits_charged = -1 * (
            user.transactions.filter(amount__lt=0).aggregate(Sum("amount"))[
                "amount__sum"
            ]
            or 0
        )
        return f"{credits_charged} Credits"

    @admin.display(description="Total Usage Cost")
    def total_usage_cost(self, user: models.AppUser):
        total_cost = (
            UsageCost.objects.filter(saved_run__uid=user.uid).aggregate(
                Sum("dollar_amount")
            )["dollar_amount__sum"]
            or 0
        )
        return round(total_cost, 2)

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


@admin.register(models.AppUserTransaction)
class AppUserTransactionAdmin(admin.ModelAdmin):
    autocomplete_fields = ["user"]
    list_display = [
        "invoice_id",
        "user",
        "amount",
        "dollar_amount",
        "end_balance",
        "payment_provider",
        "reason",
        "plan",
        "created_at",
    ]
    readonly_fields = ["created_at"]
    list_filter = [
        "reason",
        ("payment_provider", admin.EmptyFieldListFilter),
        "payment_provider",
        "plan",
        "created_at",
    ]
    inlines = [SavedRunInline]
    ordering = ["-created_at"]
    search_fields = ["invoice_id"]

    @admin.display(description="Charged Amount")
    def dollar_amount(self, obj: models.AppUserTransaction):
        if not obj.payment_provider:
            return
        return f"${obj.charged_amount / 100}"


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = readonly_fields = [
        "action_time",
        "user",
        "action_flag",
        "content_type",
        "object_repr",
        "object_id",
        "change_message",
    ]

    # to have a date-based drilldown navigation in the admin page
    date_hierarchy = "action_time"

    # to filter the results by users, content types and action flags
    list_filter = ["action_time", "user", "content_type", "action_flag"]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = ["object_repr", "change_message"]
