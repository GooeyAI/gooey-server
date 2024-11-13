from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.db.models import Sum

from api_keys.models import ApiKey
from app_users import models
from bots.admin_links import open_in_new_tab, list_related_html_url, change_obj_url
from bots.models import SavedRun, PublishedRun
from embeddings.models import EmbeddedFile
from usage_costs.models import UsageCost
from workspaces.admin import WorkspaceAdmin, WorkspaceMembershipInline


@admin.register(models.AppUser)
class AppUserAdmin(admin.ModelAdmin):
    deprecated_fields = (
        "balance",
        "is_paying",
        "stripe_customer_id",
        "subscription",
        "low_balance_email_sent_at",
    )
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "uid",
                    ("email", "phone_number"),
                    "personal_workspace",
                    ("total_payments", "total_charged", "total_usage_cost"),
                    (
                        "is_disabled",
                        "is_anonymous",
                    ),
                    (
                        "disable_safety_checker",
                        "disable_rate_limits",
                    ),
                    (
                        "view_saved_runs",
                        "view_published_runs",
                        "view_api_keys",
                        "view_embedded_files",
                        "view_transactions",
                    ),
                    ("created_at", "updated_at", "upgraded_from_anonymous_at"),
                    ("open_in_firebase", "open_in_stripe"),
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
        (
            "Deprecated",
            {
                "fields": (deprecated_fields,),
            },
        ),
    ]
    list_display = [
        "uid",
        "handle",
        "display_name",
        "email",
        "phone_number",
        "personal_workspace",
        "created_at",
    ]
    search_fields = [
        "uid",
        "display_name",
        "email",
        "phone_number",
        "handle__name",
    ]
    list_filter = [
        "is_anonymous",
        "is_disabled",
        "created_at",
        "upgraded_from_anonymous_at",
    ]
    readonly_fields = [
        "total_payments",
        "total_charged",
        "total_usage_cost",
        "created_at",
        "updated_at",
        "upgraded_from_anonymous_at",
        "view_saved_runs",
        "view_published_runs",
        "view_api_keys",
        "view_embedded_files",
        "view_transactions",
        "open_in_firebase",
        "open_in_stripe",
        "personal_workspace",
    ]
    autocomplete_fields = ["handle", "subscription"]
    inlines = [WorkspaceMembershipInline]

    @admin.display(description="User Runs")
    def view_saved_runs(self, user: models.AppUser):
        return list_related_html_url(
            SavedRun.objects.filter(uid=user.uid),
            query_param="uid",
            instance_id=user.uid,
            show_add=False,
        )

    @admin.display(description="Published Runs")
    def view_published_runs(self, user: models.AppUser):
        return list_related_html_url(
            PublishedRun.objects.filter(created_by=user),
            query_param="created_by",
            instance_id=user.id,
            show_add=False,
        )

    @admin.display(description="API Keys")
    def view_api_keys(self, user: models.AppUser):
        return list_related_html_url(
            ApiKey.objects.filter(created_by=user),
            query_param="created_by",
            instance_id=user.id,
            show_add=False,
        )

    @admin.display(description="Embedded Files")
    def view_embedded_files(self, user: models.AppUser):
        return list_related_html_url(
            EmbeddedFile.objects.filter(created_by=user),
            query_param="created_by",
            instance_id=user.id,
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

    @admin.display(description="Open in Stripe")
    def open_in_stripe(self, user: models.AppUser):
        return WorkspaceAdmin.open_in_stripe(
            self, user.get_or_create_personal_workspace()[0]
        )

    @admin.display(description="View transactions")
    def view_transactions(self, user: models.AppUser):
        return list_related_html_url(user.transactions, show_add=False)

    @admin.display(description="Personal Account")
    def personal_workspace(self, user: models.AppUser):
        workspace = user.get_or_create_personal_workspace()[0]
        return change_obj_url(
            workspace,
            label=f"Bal = {workspace.balance} | Paid = {workspace.is_paying} | Sub = {workspace.subscription}",
        )


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
    autocomplete_fields = ["user", "workspace"]
    list_display = [
        "invoice_id",
        "workspace",
        "user",
        "amount",
        "dollar_amount",
        "end_balance",
        "payment_provider",
        "reason",
        "plan",
        "created_at",
    ]
    readonly_fields = ["view_payment_provider_url", "created_at"]
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

    @admin.display(description="Payment Provider URL")
    def view_payment_provider_url(self, txn: models.AppUserTransaction):
        url = txn.payment_provider_url()
        if url:
            return open_in_new_tab(url, label=url)
        else:
            raise txn.DoesNotExist


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
