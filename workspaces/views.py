from __future__ import annotations

import html as html_lib

import gooey_gui as gui
from django.core.exceptions import ValidationError

from .models import Workspace, WorkspaceInvitation, WorkspaceMembership, WorkspaceRole
from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_route_path


DEFAULT_WORKSPACE_LOGO = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/74a37c52-8260-11ee-a297-02420a0001ee/gooey.ai%20-%20A%20pop%20art%20illustration%20of%20robots%20taki...y%20Liechtenstein%20mint%20colour%20is%20main%20city%20Seattle.png"


rounded_border = "w-100 border shadow-sm rounded py-4 px-3"


def invitation_page(user: AppUser, invitation: WorkspaceInvitation):
    from routers.account import workspaces_route

    workspaces_page_path = get_route_path(workspaces_route)

    with gui.div(className="text-center my-5"):
        gui.write(
            f"# Invitation to join {invitation.workspace.name}",
            className="d-block mb-5",
        )

        if invitation.workspace.memberships.filter(user=user).exists():
            # redirect to workspace page
            raise gui.RedirectException(workspaces_page_path)

        if invitation.status != WorkspaceInvitation.Status.PENDING:
            gui.write(f"This invitation has been {invitation.get_status_display()}.")
            return

        gui.write(
            f"**{format_user_name(invitation.inviter)}** has invited you to join **{invitation.workspace.name}**."
        )

        if other_m := user.workspace_memberships.first():
            gui.caption(
                f"You are currently a member of [{other_m.workspace.name}]({workspaces_page_path}). You will be removed from that team if you accept this invitation."
            )
            accept_label = "Leave and Accept"
        else:
            accept_label = "Accept"

        with gui.div(
            className="d-flex justify-content-center align-items-center mx-auto",
            style={"max-width": "600px"},
        ):
            accept_button = gui.button(accept_label, type="primary", className="w-50")
            reject_button = gui.button("Decline", type="secondary", className="w-50")

        if accept_button:
            invitation.accept(user=user)
            raise gui.RedirectException(workspaces_page_path)
        if reject_button:
            invitation.reject(user=user)


def workspaces_page(user: AppUser):
    memberships = user.workspace_memberships.filter()
    if not memberships:
        gui.write("*You're not part of an workspaceanization yet... Create one?*")

        render_workspace_creation_view(user)
    else:
        # only support one workspace for now
        render_workspace_by_membership(memberships.first())


def render_workspace_by_membership(membership: WorkspaceMembership):
    """
    membership object has all the information we need:
        - workspace
        - current user
        - current user's role in the workspace (and other metadata)
    """
    workspace = membership.workspace
    current_user = membership.user

    with gui.div(
        className="d-xs-block d-sm-flex flex-row-reverse justify-content-between"
    ):
        with gui.div(className="d-flex justify-content-center align-items-center"):
            if membership.can_edit_workspace_metadata():
                workspace_edit_modal = gui.Modal(
                    "Edit Workspace", key="edit-workspace-modal"
                )
                if workspace_edit_modal.is_open():
                    with workspace_edit_modal.container():
                        render_workspace_edit_view_by_membership(
                            membership, modal=workspace_edit_modal
                        )

                if gui.button(f"{icons.edit} Edit", type="secondary"):
                    workspace_edit_modal.open()

        with gui.div(className="d-flex align-items-center"):
            gui.image(
                workspace.logo or DEFAULT_WORKSPACE_LOGO,
                className="my-0 me-4 rounded",
                style={"width": "128px", "height": "128px", "object-fit": "contain"},
            )
            with gui.div(className="d-flex flex-column justify-content-center"):
                gui.write(f"# {workspace.name}")
                if workspace.domain_name:
                    gui.write(
                        f"Workspace Domain: `@{workspace.domain_name}`",
                        className="text-muted",
                    )

    with gui.div(className="mt-4"):
        with gui.div(className="d-flex justify-content-between align-items-center"):
            gui.write("## Members")

            if membership.can_invite():
                invite_modal = gui.Modal("Invite Member", key="invite-member-modal")
                if gui.button(f"{icons.add_user} Invite"):
                    invite_modal.open()

                if invite_modal.is_open():
                    with invite_modal.container():
                        render_invite_creation_view(
                            workspace=workspace,
                            inviter=current_user,
                            modal=invite_modal,
                        )

        render_members_list(workspace=workspace, current_member=membership)

    with gui.div(className="mt-4"):
        render_pending_invitations_list(workspace=workspace, current_member=membership)

    with gui.div(className="mt-4"):
        workspace_leave_modal = gui.Modal(
            "Leave Workspace", key="leave-workspace-modal"
        )
        if workspace_leave_modal.is_open():
            with workspace_leave_modal.container():
                render_workspace_leave_view_by_membership(
                    membership, modal=workspace_leave_modal
                )

        with gui.div(className="text-end"):
            leave_workspace = gui.button(
                "Leave",
                className="btn btn-theme bg-danger border-danger text-white",
            )
        if leave_workspace:
            workspace_leave_modal.open()


def render_workspace_creation_view(user: AppUser):
    gui.write(f"# {icons.company} Create an Workspace", unsafe_allow_html=True)
    workspace_fields = render_workspace_create_or_edit_form()

    if gui.button("Create"):
        try:
            Workspace.objects.create_workspace(
                created_by=user,
                **workspace_fields,
            )
        except ValidationError as e:
            gui.write(", ".join(e.messages), className="text-danger")
        else:
            gui.rerun()


def render_workspace_edit_view_by_membership(
    membership: WorkspaceMembership, *, modal: gui.Modal
):
    workspace = membership.workspace
    render_workspace_create_or_edit_form(workspace=workspace)

    if gui.button("Save", className="w-100", type="primary"):
        try:
            workspace.full_clean()
        except ValidationError as e:
            # newlines in markdown
            gui.write("  \n".join(e.messages), className="text-danger")
        else:
            workspace.save()
            modal.close()

    if membership.can_delete_workspace() or membership.can_transfer_ownership():
        gui.write("---")
        render_danger_zone_by_membership(membership)


def render_danger_zone_by_membership(membership: WorkspaceMembership):
    gui.write("### Danger Zone", className="d-block my-2")

    if membership.can_delete_workspace():
        workspace_deletion_modal = gui.Modal(
            "Delete Workspaceanization", key="delete-workspace-modal"
        )
        if workspace_deletion_modal.is_open():
            with workspace_deletion_modal.container():
                render_workspace_deletion_view_by_membership(
                    membership, modal=workspace_deletion_modal
                )

        with gui.div(className="d-flex justify-content-between align-items-center"):
            gui.write("Delete Workspaceanization")
            if gui.button(
                f"{icons.delete} Delete",
                className="btn btn-theme py-2 bg-danger border-danger text-white",
            ):
                workspace_deletion_modal.open()


def render_workspace_deletion_view_by_membership(
    membership: WorkspaceMembership, *, modal: gui.Modal
):
    gui.write(
        f"Are you sure you want to delete **{membership.workspace.name}**? This action is irreversible."
    )

    with gui.div(className="d-flex"):
        if gui.button(
            "Cancel", type="secondary", className="border-danger text-danger w-50"
        ):
            modal.close()

        if gui.button(
            "Delete", className="btn btn-theme bg-danger border-danger text-light w-50"
        ):
            membership.workspace.delete()
            modal.close()


def render_workspace_leave_view_by_membership(
    current_member: WorkspaceMembership, *, modal: gui.Modal
):
    workspace = current_member.workspace

    gui.write("Are you sure you want to leave this workspaceanization?")

    new_owner = None
    if (
        current_member.role == WorkspaceRole.OWNER
        and workspace.memberships.count() == 1
    ):
        gui.caption(
            "You are the only member. You will lose access to this team if you leave."
        )
    elif (
        current_member.role == WorkspaceRole.OWNER
        and workspace.memberships.filter(role=WorkspaceRole.OWNER).count() == 1
    ):
        members_by_uid = {
            m.user.uid: m
            for m in workspace.memberships.all().select_related("user")
            if m != current_member
        }

        gui.caption(
            "You are the only owner of this workspaceanization. Please choose another member to promote to owner."
        )
        new_owner_uid = gui.selectbox(
            "New Owner",
            options=list(members_by_uid),
            format_func=lambda uid: format_user_name(members_by_uid[uid].user),
        )
        new_owner = members_by_uid[new_owner_uid]

    with gui.div(className="d-flex"):
        if gui.button(
            "Cancel", type="secondary", className="border-danger text-danger w-50"
        ):
            modal.close()

        if gui.button(
            "Leave", className="btn btn-theme bg-danger border-danger text-light w-50"
        ):
            if new_owner:
                new_owner.role = WorkspaceRole.OWNER
                new_owner.save()
            current_member.delete()
            modal.close()


def render_members_list(workspace: Workspace, current_member: WorkspaceMembership):
    with gui.tag("table", className="table table-responsive"):
        with gui.tag("thead"), gui.tag("tr"):
            with gui.tag("th", scope="col"):
                gui.html("Name")
            with gui.tag("th", scope="col"):
                gui.html("Role")
            with gui.tag("th", scope="col"):
                gui.html(f"{icons.time} Since")
            with gui.tag("th", scope="col"):
                gui.html("")

        with gui.tag("tbody"):
            for m in workspace.memberships.all().order_by("created_at"):
                with gui.tag("tr"):
                    with gui.tag("td"):
                        name = format_user_name(
                            m.user, current_user=current_member.user
                        )
                        if m.user.handle_id:
                            with gui.link(to=m.user.handle.get_app_url()):
                                gui.html(html_lib.escape(name))
                        else:
                            gui.html(html_lib.escape(name))
                    with gui.tag("td"):
                        gui.html(m.get_role_display())
                    with gui.tag("td"):
                        gui.html(m.created_at.strftime("%b %d, %Y"))
                    with gui.tag("td", className="text-end"):
                        render_membership_actions(m, current_member=current_member)


def render_membership_actions(
    m: WorkspaceMembership, current_member: WorkspaceMembership
):
    if current_member.can_change_role(m):
        if m.role == WorkspaceRole.MEMBER:
            modal, confirmed = button_with_confirmation_modal(
                f"{icons.admin} Make Admin",
                key=f"promote-member-{m.pk}",
                unsafe_allow_html=True,
                confirmation_text=f"Are you sure you want to promote **{format_user_name(m.user)}** to an admin?",
                modal_title="Make Admin",
                modal_key=f"promote-member-{m.pk}-modal",
            )
            if confirmed:
                m.role = WorkspaceRole.ADMIN
                m.save()
                modal.close()
        elif m.role == WorkspaceRole.ADMIN:
            modal, confirmed = button_with_confirmation_modal(
                f"{icons.remove_user} Revoke Admin",
                key=f"demote-member-{m.pk}",
                unsafe_allow_html=True,
                confirmation_text=f"Are you sure you want to revoke admin privileges from **{format_user_name(m.user)}**?",
                modal_title="Revoke Admin",
                modal_key=f"demote-member-{m.pk}-modal",
            )
            if confirmed:
                m.role = WorkspaceRole.MEMBER
                m.save()
                modal.close()

    if current_member.can_kick(m):
        modal, confirmed = button_with_confirmation_modal(
            f"{icons.remove_user} Remove",
            key=f"remove-member-{m.pk}",
            unsafe_allow_html=True,
            confirmation_text=f"Are you sure you want to remove **{format_user_name(m.user)}** from **{m.workspace.name}**?",
            modal_title="Remove Member",
            modal_key=f"remove-member-{m.pk}-modal",
            className="bg-danger border-danger text-light",
        )
        if confirmed:
            m.delete()
            modal.close()


def button_with_confirmation_modal(
    btn_label: str,
    confirmation_text: str,
    modal_title: str | None = None,
    modal_key: str | None = None,
    modal_className: str = "",
    **btn_props,
) -> tuple[gui.Modal, bool]:
    """
    Returns boolean for whether user confirmed the action or not.
    """

    modal = gui.Modal(modal_title or btn_label, key=modal_key)

    btn_classes = "btn btn-theme btn-sm my-0 py-0 " + btn_props.pop("className", "")
    if gui.button(btn_label, className=btn_classes, **btn_props):
        modal.open()

    if modal.is_open():
        with modal.container(className=modal_className):
            gui.write(confirmation_text)
            with gui.div(className="d-flex"):
                if gui.button(
                    "Cancel",
                    type="secondary",
                    className="border-danger text-danger w-50",
                ):
                    modal.close()

                confirmed = gui.button(
                    "Confirm",
                    className="btn btn-theme bg-danger border-danger text-light w-50",
                )
                return modal, confirmed

    return modal, False


def render_pending_invitations_list(
    workspace: Workspace, *, current_member: WorkspaceMembership
):
    pending_invitations = workspace.invitations.filter(
        status=WorkspaceInvitation.Status.PENDING
    )
    if not pending_invitations:
        return

    gui.write("## Pending")
    with gui.tag("table", className="table table-responsive"):
        with gui.tag("thead"), gui.tag("tr"):
            with gui.tag("th", scope="col"):
                gui.html("Email")
            with gui.tag("th", scope="col"):
                gui.html("Invited By")
            with gui.tag("th", scope="col"):
                gui.html(f"{icons.time} Last invited on")
            with gui.tag("th", scope="col"):
                pass

        with gui.tag("tbody"):
            for invite in pending_invitations:
                with gui.tag("tr", className="text-break"):
                    with gui.tag("td"):
                        gui.html(html_lib.escape(invite.invitee_email))
                    with gui.tag("td"):
                        gui.html(
                            html_lib.escape(
                                format_user_name(
                                    invite.inviter, current_user=current_member.user
                                )
                            )
                        )
                    with gui.tag("td"):
                        last_invited_at = invite.last_email_sent_at or invite.created_at
                        gui.html(last_invited_at.strftime("%b %d, %Y"))
                    with gui.tag("td", className="text-end"):
                        render_invitation_actions(invite, current_member=current_member)


def render_invitation_actions(
    invitation: WorkspaceInvitation, current_member: WorkspaceMembership
):
    if current_member.can_invite() and invitation.can_resend_email():
        modal, confirmed = button_with_confirmation_modal(
            f"{icons.email} Resend",
            className="btn btn-theme btn-sm my-0 py-0",
            key=f"resend-invitation-{invitation.pk}",
            unsafe_allow_html=True,
            confirmation_text=f"Resend invitation to **{invitation.invitee_email}**?",
            modal_title="Resend Invitation",
            modal_key=f"resend-invitation-{invitation.pk}-modal",
        )
        if confirmed:
            try:
                invitation.send_email()
            except ValidationError as e:
                pass
            finally:
                modal.close()

    if current_member.can_invite():
        modal, confirmed = button_with_confirmation_modal(
            f"{icons.delete} Cancel",
            key=f"cancel-invitation-{invitation.pk}",
            unsafe_allow_html=True,
            confirmation_text=f"Are you sure you want to cancel the invitation to **{invitation.invitee_email}**?",
            modal_title="Cancel Invitation",
            modal_key=f"cancel-invitation-{invitation.pk}-modal",
            className="bg-danger border-danger text-light",
        )
        if confirmed:
            invitation.cancel(user=current_member.user)
            modal.close()


def render_invite_creation_view(
    workspace: Workspace, inviter: AppUser, modal: gui.Modal
):
    email = gui.text_input("Email")
    if workspace.domain_name:
        gui.caption(
            f"Users with `@{workspace.domain_name}` email will be added automatically."
        )

    if gui.button(f"{icons.add_user} Invite", type="primary", unsafe_allow_html=True):
        try:
            workspace.invite_user(
                invitee_email=email,
                inviter=inviter,
                role=WorkspaceRole.MEMBER,
                auto_accept=workspace.domain_name.lower()
                == email.split("@")[1].lower(),
            )
        except ValidationError as e:
            gui.write(", ".join(e.messages), className="text-danger")
        else:
            modal.close()


def render_workspace_create_or_edit_form(
    workspace: Workspace | None = None,
) -> AttrDict | Workspace:
    workspace_proxy = workspace or AttrDict()

    workspace_proxy.name = gui.text_input(
        "Team Name", value=workspace and workspace.name or ""
    )
    workspace_proxy.logo = gui.file_uploader(
        "Logo", accept=["image/*"], value=workspace and workspace.logo or ""
    )
    workspace_proxy.domain_name = gui.text_input(
        "Domain Name (Optional)",
        placeholder="e.g. gooey.ai",
        value=workspace and workspace.domain_name or "",
    )
    if workspace_proxy.domain_name:
        gui.caption(
            f"Invite any user with `@{workspace_proxy.domain_name}` email to this workspaceanization."
        )

    return workspace_proxy


def format_user_name(user: AppUser, current_user: AppUser | None = None):
    name = user.display_name or user.first_name()
    if current_user and user == current_user:
        name += " (You)"
    return name


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def left_and_right(*, className: str = "", **props):
    className += " d-flex flex-row justify-content-between align-items-center"
    with gui.div(className=className, **props):
        return gui.div(), gui.div()
