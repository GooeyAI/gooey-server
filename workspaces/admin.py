from django.contrib import admin
from django.db.models import Sum
from safedelete.admin import SafeDeleteAdmin, SafeDeleteAdminFilter

from bots.admin_links import change_obj_url
from usage_costs.models import UsageCost
from .models import Workspace, WorkspaceMembership, WorkspaceInvitation


class WorkspaceMembershipInline(admin.TabularInline):
    model = WorkspaceMembership
    extra = 0
    show_change_link = True
    fields = ["user", "role", "created_at", "updated_at"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]
    can_delete = False
    show_change_link = True


class WorkspaceInvitationInline(admin.TabularInline):
    model = WorkspaceInvitation
    extra = 0
    show_change_link = True
    fields = [
        "invitee_email",
        "inviter",
        "status",
        "auto_accepted",
        "created_at",
        "updated_at",
    ]
    readonly_fields = ["auto_accepted", "created_at", "updated_at"]
    ordering = ["status", "-created_at"]
    can_delete = False
    show_change_link = True


@admin.register(Workspace)
class WorkspaceAdmin(SafeDeleteAdmin):
    list_display = [
        "name",
        "domain_name",
        "created_at",
        "updated_at",
    ] + list(SafeDeleteAdmin.list_display)
    list_filter = [SafeDeleteAdminFilter] + list(SafeDeleteAdmin.list_filter)
    fields = [
        "name",
        "domain_name",
        "created_by",
        "is_personal",
        "is_paying",
        ("balance", "subscription"),
        ("total_payments", "total_charged", "total_usage_cost"),
        "created_at",
        "updated_at",
    ]
    search_fields = ["name", "domain_name"]
    readonly_fields = [
        "is_personal",
        "created_at",
        "updated_at",
        "total_payments",
        "total_charged",
        "total_usage_cost",
    ]
    inlines = [WorkspaceMembershipInline, WorkspaceInvitationInline]
    ordering = ["-created_at"]

    @admin.display(description="Total Payments")
    def total_payments(self, workspace: Workspace):
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
    def total_charged(self, workspace: Workspace):
        credits_charged = -1 * (
            workspace.transactions.filter(amount__lt=0).aggregate(Sum("amount"))[
                "amount__sum"
            ]
            or 0
        )
        return f"{credits_charged} Credits"

    @admin.display(description="Total Usage Cost")
    def total_usage_cost(self, workspace: Workspace):
        total_cost = (
            UsageCost.objects.filter(
                saved_run__billed_workspace_id=workspace.id
            ).aggregate(Sum("dollar_amount"))["dollar_amount__sum"]
            or 0
        )
        return round(total_cost, 2)


@admin.register(WorkspaceMembership)
class WorkspaceMembershipAdmin(SafeDeleteAdmin):
    list_display = [
        "user",
        "workspace",
        "role",
        "created_at",
        "updated_at",
    ] + list(SafeDeleteAdmin.list_display)
    list_filter = ["workspace", "role", SafeDeleteAdminFilter] + list(
        SafeDeleteAdmin.list_filter
    )

    def get_readonly_fields(
        self, request: "HttpRequest", obj: WorkspaceMembership | None = None
    ) -> list[str]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.workspace and obj.workspace.deleted:
            return readonly_fields + ["deleted_workspace"]
        else:
            return readonly_fields

    @admin.display
    def deleted_workspace(self, obj):
        workspace = Workspace.deleted_objects.get(pk=obj.workspace_id)
        return change_obj_url(workspace)


@admin.register(WorkspaceInvitation)
class WorkspaceInvitationAdmin(SafeDeleteAdmin):
    fields = [
        "workspace",
        "invitee_email",
        "inviter",
        "role",
        "status",
        "auto_accepted",
        "created_at",
        "updated_at",
    ]
    list_display = [
        "workspace",
        "invitee_email",
        "inviter",
        "status",
        "created_at",
        "updated_at",
    ] + list(SafeDeleteAdmin.list_display)
    list_filter = ["workspace", "inviter", "role", SafeDeleteAdminFilter] + list(
        SafeDeleteAdmin.list_filter
    )
    readonly_fields = ["auto_accepted"]
