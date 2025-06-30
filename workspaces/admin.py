import typing

from django.contrib import admin
from django.db.models import Sum, Q
from safedelete.admin import SafeDeleteAdmin, SafeDeleteAdminFilter

from api_keys.models import ApiKey
from bots.admin_links import change_obj_url, open_in_new_tab, list_related_html_url
from bots.models import SavedRun
from bots.models.published_run import PublishedRun
from embeddings.models import EmbeddedFile
from payments.models import Subscription
from usage_costs.models import UsageCost
from . import models

if typing.TYPE_CHECKING:
    from django.http import HttpRequest


class WorkspaceMembershipInline(admin.TabularInline):
    model = models.WorkspaceMembership
    extra = 0
    autocomplete_fields = ["user", "workspace"]
    readonly_fields = ["invite", "created_at", "updated_at"]
    ordering = ["-created_at"]


@admin.register(models.WorkspaceInvite)
class WorkspaceInviteAdmin(admin.ModelAdmin):
    list_display = [
        "workspace",
        "email",
        "status",
        "has_expired",
        "clicks",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    ]
    list_filter = ["created_at", "status"]
    readonly_fields = [
        "clicks",
        "auto_accepted",
        "has_expired",
        "created_at",
        "updated_at",
    ]
    autocomplete_fields = ["workspace", "created_by", "updated_by"]


class WorkspaceInviteInline(admin.TabularInline):
    model = models.WorkspaceInvite
    extra = 0
    autocomplete_fields = WorkspaceInviteAdmin.autocomplete_fields
    readonly_fields = ["auto_accepted", "clicks", "created_at", "updated_at"]
    ordering = ["status", "-created_at"]


@admin.register(models.Workspace)
class WorkspaceAdmin(SafeDeleteAdmin):
    list_display = [
        "display_name",
        "is_personal",
        "created_by",
        "handle",
        "is_paying",
        "balance",
        "subscription",
        "domain_name",
        "created_at",
        "updated_at",
        "onedrive_user_name",
        "onedrive_access_token",
        "onedrive_refresh_token",
    ] + list(SafeDeleteAdmin.list_display)
    list_filter = (
        [
            "is_personal",
            "is_paying",
        ]
        + [SafeDeleteAdminFilter]
        + list(SafeDeleteAdmin.list_filter)
    )
    fields = [
        "name",
        "description",
        "domain_name",
        "handle",
        "created_by",
        "is_personal",
        ("is_paying", "stripe_customer_id"),
        ("total_payments", "total_charged", "total_usage_cost"),
        ("balance", "subscription"),
        (
            "view_saved_runs",
            "view_published_runs",
            "view_api_keys",
            "view_embedded_files",
        ),
        ("created_at", "updated_at"),
        "open_in_stripe",
        "onedrive_user_name",
        "onedrive_access_token",
        "onedrive_refresh_token",
    ]
    search_fields = [
        "name",
        "domain_name",
        "created_by__uid",
        "created_by__display_name",
        "created_by__email",
        "created_by__phone_number",
        "handle__name",
    ]
    readonly_fields = [
        "is_personal",
        "created_at",
        "updated_at",
        "view_saved_runs",
        "view_published_runs",
        "view_api_keys",
        "view_embedded_files",
        "total_payments",
        "total_charged",
        "total_usage_cost",
        "open_in_stripe",
    ]
    inlines = [WorkspaceMembershipInline, WorkspaceInviteInline]
    ordering = ["-created_at"]
    autocomplete_fields = ["created_by", "handle"]

    def get_form(self, request, obj=None, change=False, **kwargs):
        self.obj = obj
        return super().get_form(request, obj, change, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "subscription" and self.obj:
            kwargs["queryset"] = Subscription.objects.filter(
                Q(workspace=self.obj) | Q(workspace__isnull=True)
            )[:10]
        return field

    @admin.display(description="Name")
    def display_name(self, workspace: models.Workspace):
        return workspace.display_name()

    @admin.display(description="User Runs")
    def view_saved_runs(self, workspace: models.Workspace):
        return list_related_html_url(
            SavedRun.objects.filter(workspace=workspace),
            query_param="workspace__id__exact",
            instance_id=workspace.id,
            show_add=False,
        )

    @admin.display(description="Published Runs")
    def view_published_runs(self, workspace: models.Workspace):
        return list_related_html_url(
            PublishedRun.objects.filter(workspace=workspace),
            query_param="workspace__id__exact",
            instance_id=workspace.id,
            show_add=False,
        )

    @admin.display(description="API Keys")
    def view_api_keys(self, workspace: models.Workspace):
        return list_related_html_url(
            ApiKey.objects.filter(workspace=workspace),
            query_param="workspace__id__exact",
            instance_id=workspace.id,
            show_add=False,
        )

    @admin.display(description="Embedded Files")
    def view_embedded_files(self, workspace: models.Workspace):
        return list_related_html_url(
            EmbeddedFile.objects.filter(workspace=workspace),
            query_param="workspace__id__exact",
            instance_id=workspace.id,
            show_add=False,
        )

    @admin.display(description="Total Payments")
    def total_payments(self, workspace: models.Workspace):
        return "$" + str(
            (
                workspace.transactions.aggregate(Sum("charged_amount"))[
                    "charged_amount__sum"
                ]
                or 0
            )
            / 100
        )

    @admin.display(description="Total Charged")
    def total_charged(self, workspace: models.Workspace):
        credits_charged = -1 * (
            workspace.transactions.filter(amount__lt=0).aggregate(Sum("amount"))[
                "amount__sum"
            ]
            or 0
        )
        return f"{credits_charged} Credits"

    @admin.display(description="Total Usage Cost")
    def total_usage_cost(self, workspace: models.Workspace):
        total_cost = (
            UsageCost.objects.filter(saved_run__workspace=workspace).aggregate(
                Sum("dollar_amount")
            )["dollar_amount__sum"]
            or 0
        )
        return round(total_cost, 2)

    @admin.display(description="Open in Stripe")
    def open_in_stripe(self, workspace: models.Workspace):
        if not workspace.stripe_customer_id:
            # Try to find the customer ID.
            workspace.search_stripe_customer()
        if not workspace.stripe_customer_id:
            # If we still don't have a customer ID, return None.
            raise AttributeError("No Stripe customer ID found.")
        return open_in_new_tab(
            f"https://dashboard.stripe.com/customers/{workspace.stripe_customer_id}",
            label=workspace.stripe_customer_id,
        )


@admin.register(models.WorkspaceMembership)
class WorkspaceMembershipAdmin(SafeDeleteAdmin):
    list_display = [
        "user",
        "workspace",
        "role",
        "created_at",
        "updated_at",
    ] + list(SafeDeleteAdmin.list_display)
    list_filter = ["role", SafeDeleteAdminFilter] + list(SafeDeleteAdmin.list_filter)

    def get_readonly_fields(
        self, request: "HttpRequest", obj: models.WorkspaceMembership | None = None
    ) -> list[str]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.workspace and obj.workspace.deleted:
            return readonly_fields + ["deleted_workspace"]
        else:
            return readonly_fields

    @admin.display
    def deleted_workspace(self, obj):
        workspace = models.Workspace.deleted_objects.get(pk=obj.workspace_id)
        return change_obj_url(workspace)
