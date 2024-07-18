from django.contrib import admin
from safedelete.admin import SafeDeleteAdmin, SafeDeleteAdminFilter

from bots.admin_links import change_obj_url
from orgs.models import Org, OrgMembership, OrgInvitation


class OrgMembershipInline(admin.TabularInline):
    model = OrgMembership
    extra = 0
    show_change_link = True
    fields = ["user", "role", "created_at", "updated_at"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]
    can_delete = False
    show_change_link = True


class OrgInvitationInline(admin.TabularInline):
    model = OrgInvitation
    extra = 0
    show_change_link = True
    fields = [
        "invitee_email",
        "inviter",
        "role",
        "status",
        "auto_accepted",
        "created_at",
        "updated_at",
    ]
    readonly_fields = ["auto_accepted", "created_at", "updated_at"]
    ordering = ["status", "-created_at"]
    can_delete = False
    show_change_link = True


@admin.register(Org)
class OrgAdmin(SafeDeleteAdmin):
    list_display = [
        "name",
        "domain_name",
        "created_at",
        "updated_at",
    ] + list(SafeDeleteAdmin.list_display)
    list_filter = [SafeDeleteAdminFilter] + list(SafeDeleteAdmin.list_filter)
    fields = ["name", "domain_name", "created_by", "created_at", "updated_at"]
    search_fields = ["name", "domain_name"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [OrgMembershipInline, OrgInvitationInline]
    ordering = ["-created_at"]


@admin.register(OrgMembership)
class OrgMembershipAdmin(SafeDeleteAdmin):
    list_display = [
        "user",
        "org",
        "role",
        "created_at",
        "updated_at",
    ] + list(SafeDeleteAdmin.list_display)
    list_filter = ["org", "role", SafeDeleteAdminFilter] + list(
        SafeDeleteAdmin.list_filter
    )

    def get_readonly_fields(
        self, request: "HttpRequest", obj: OrgMembership | None = None
    ) -> list[str]:
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.org and obj.org.deleted:
            return readonly_fields + ["deleted_org"]
        else:
            return readonly_fields

    @admin.display
    def deleted_org(self, obj):
        org = Org.deleted_objects.get(pk=obj.org_id)
        return change_obj_url(org)


@admin.register(OrgInvitation)
class OrgInvitationAdmin(SafeDeleteAdmin):
    fields = [
        "org",
        "invitee_email",
        "inviter",
        "role",
        "status",
        "auto_accepted",
        "created_at",
        "updated_at",
    ]
    list_display = [
        "org",
        "invitee_email",
        "inviter",
        "status",
        "created_at",
        "updated_at",
    ] + list(SafeDeleteAdmin.list_display)
    list_filter = ["org", "inviter", "role", SafeDeleteAdminFilter] + list(
        SafeDeleteAdmin.list_filter
    )
    readonly_fields = ["auto_accepted"]
