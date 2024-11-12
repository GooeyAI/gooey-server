import html as html_lib
from copy import copy

import gooey_gui as gui
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.core.exceptions import ValidationError

from app_users.models import AppUser
from daras_ai_v2 import icons
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.fastapi_tricks import get_route_path
from daras_ai_v2.user_date_widgets import render_local_date_attrs
from payments.plans import PricingPlan
from .models import (
    DEFAULT_WORKSPACE_PHOTO_URL,
    Workspace,
    WorkspaceInvite,
    WorkspaceMembership,
    WorkspaceRole,
)
from .widgets import get_current_workspace, set_current_workspace


rounded_border = "w-100 border shadow-sm rounded py-4 px-3"


def invitation_page(current_user: AppUser, session: dict, invite: WorkspaceInvite):
    from routers.account import members_route

    workspaces_page_path = get_route_path(members_route)

    with gui.div(className="text-center my-5"):
        gui.write(
            f"# Invitation to join {invite.workspace.display_name(current_user)}",
            className="d-block mb-5",
        )

        if invite.workspace.memberships.filter(user=current_user).exists():
            # redirect to workspace page
            raise gui.RedirectException(workspaces_page_path)

        if invite.email != current_user.email:
            gui.write(
                f"Doh! This invitation is for **{invite.email}**, not you. Please log in with the correct email address.",
            )
            return

        if invite.status != WorkspaceInvite.Status.PENDING:
            gui.write(f"This invitation has been {invite.get_status_display()}.")
            return

        gui.write(f"You've been invited by **{invite.created_by.full_name()}**")
        gui.newline()

        with gui.div(
            className="d-flex justify-content-center align-items-center mx-auto",
            style={"max-width": "600px"},
        ):
            if gui.button("Decline", className="w-50"):
                invite.reject(current_user)
                gui.rerun()

            if gui.button("Accept", type="primary", className="w-50"):
                invite.accept(current_user, updated_by=current_user)
                set_current_workspace(session, int(invite.workspace_id))
                raise gui.RedirectException(workspaces_page_path)


def workspaces_page(user: AppUser, session: dict):
    from routers.account import account_route

    workspace = get_current_workspace(user, session)
    if workspace.is_personal:
        raise gui.RedirectException(get_route_path(account_route))

    membership = workspace.memberships.get(user=user)
    render_workspace_by_membership(membership)


def render_workspace_by_membership(membership: WorkspaceMembership):
    """
    membership object has all the information we need:
        - workspace
        - current user
        - current user's role in the workspace (and other metadata)
    """
    from routers.account import account_route

    workspace = membership.workspace

    with gui.div(className="d-block d-sm-flex justify-content-between"):
        col1 = gui.div(
            className="d-block d-md-flex text-center text-sm-start align-items-center"
        )
        col2 = gui.div()

    with col1:
        gui.image(
            workspace.photo_url or DEFAULT_WORKSPACE_PHOTO_URL,
            className="my-0 me-4 rounded",
            style={"width": "128px", "height": "128px", "object-fit": "contain"},
        )
        with gui.div(className="d-flex flex-column justify-content-end"):
            plan = (
                workspace.subscription
                and PricingPlan.from_sub(workspace.subscription)
                or PricingPlan.STARTER
            )

            with gui.tag("h1", className="mb-0" if workspace.domain_name else ""):
                gui.html(html_lib.escape(workspace.display_name(membership.user)))
            if workspace.domain_name:
                gui.caption(f"Domain: `@{workspace.domain_name}`")

            billing_info = f"""
                <span class="text-muted">Credits:</span> {workspace.balance}
                <span class="text-muted">Plan:</span> {plan.title}
            """.strip()
            if membership.can_edit_workspace() and plan in (
                PricingPlan.STARTER,
                PricingPlan.CREATOR,
            ):
                billing_info += f" [Upgrade]({get_route_path(account_route)})"
            gui.write(billing_info, unsafe_allow_html=True)

    if membership.can_edit_workspace():
        with col2, gui.div(className="mt-2"):
            edit_workspace_button_with_dialog(membership)

    gui.newline()

    with gui.div(className="d-flex justify-content-between align-items-center"):
        gui.write("#### Members")
        member_invite_button_with_dialog(membership)
    render_members_list(workspace=workspace, current_member=membership)

    gui.newline()

    if membership.can_invite():
        render_pending_invites_list(workspace=workspace, current_member=membership)

    can_leave = membership.can_leave_workspace()
    if not can_leave:
        return

    gui.newline()

    dialog_ref = gui.use_confirm_dialog(key="leave-workspace", close_on_confirm=False)
    with gui.div():
        gui.write("#### Danger Zone")
        with gui.div():
            if gui.button(
                label=f"{icons.sign_out} Leave",
                className="py-2 text-danger",
            ):
                dialog_ref.set_open(True)

    if dialog_ref.is_open:
        new_owner_id = render_workspace_leave_dialog(dialog_ref, membership)
    else:
        new_owner_id = None

    if dialog_ref.pressed_confirm:
        if new_owner_id:
            WorkspaceMembership.objects.filter(
                user_id=new_owner_id, workspace=membership.workspace
            ).update(
                role=WorkspaceRole.OWNER,
            )
        membership.delete()
        gui.rerun()


def member_invite_button_with_dialog(
    membership: WorkspaceMembership,
    *,
    close_on_confirm: bool = True,
    **props,
):
    if not membership.can_invite():
        return

    ref = gui.use_confirm_dialog(key="invite-member", close_on_confirm=False)

    if gui.button(label=f"{icons.add_user} Invite", **props):
        clear_invite_creation_form()
        ref.set_open(True)
    if not ref.is_open:
        return

    with gui.confirm_dialog(
        ref=ref,
        modal_title="#### Invite Member",
        confirm_label=f"{icons.send} Send Invite",
    ):
        role, email = render_invite_creation_form(membership.workspace)
        if not ref.pressed_confirm:
            return

        try:
            WorkspaceInvite.objects.create_and_send_invite(
                workspace=membership.workspace,
                email=email,
                current_user=membership.user,
                defaults=dict(role=role),
            )
        except ValidationError as e:
            gui.write("\n".join(e.messages), className="text-danger")
        else:
            if close_on_confirm:
                ref.set_open(False)
                gui.rerun()
            else:
                gui.success("Invite sent successfully!")


def edit_workspace_button_with_dialog(membership: WorkspaceMembership):
    if not membership.can_edit_workspace():
        return

    ref = gui.use_confirm_dialog(key="edit-workspace", close_on_confirm=False)

    if gui.button(label=f"{icons.edit} Edit"):
        clear_workspace_create_or_edit_form()
        ref.set_open(True)
    if not ref.is_open:
        return

    with gui.confirm_dialog(
        ref=ref,
        modal_title="#### Edit Workspace",
        confirm_label=f"{icons.save} Save",
    ):
        workspace_copy = render_workspace_edit_view_by_membership(ref, membership)

        if not ref.pressed_confirm:
            return
        try:
            workspace_copy.full_clean()
        except ValidationError as e:
            # newlines in markdown
            gui.write("\n".join(e.messages), className="text-danger")
        else:
            workspace_copy.save()
            membership.workspace.refresh_from_db()
            ref.set_open(False)
            gui.rerun()


def render_workspace_edit_view_by_membership(
    dialog_ref: gui.ConfirmDialogRef, membership: WorkspaceMembership
):
    workspace = copy(membership.workspace)
    render_workspace_create_or_edit_form(workspace, membership.user)
    render_danger_zone_by_membership(dialog_ref, membership)
    return workspace


def clear_invite_creation_form():
    keys = {k for k in gui.session_state.keys() if k.startswith("invite-form-")}
    for k in keys:
        gui.session_state.pop(k, None)


def render_invite_creation_form(workspace: Workspace) -> tuple[str, str]:
    gui.write(f"Invite to **{workspace.display_name()}**.")

    email = gui.text_input(
        "###### Email",
        style=dict(minWidth="300px"),
        key="invite-form-email",
    ).strip()

    role = gui.selectbox(
        "###### Role",
        options=WorkspaceRole,
        format_func=WorkspaceRole.display_html,
        value=WorkspaceRole.ADMIN.value,
        key="invite-form-role",
    )

    if workspace.domain_name:
        gui.caption(
            f"Users with `@{workspace.domain_name}` email will be added automatically."
        )

    return role, email


def render_danger_zone_by_membership(
    parent_dialog: gui.ConfirmDialogRef, membership: WorkspaceMembership
):
    if not membership.can_delete_workspace():
        return
    with gui.expander("💀 Danger Zone"):
        with gui.div(className="d-flex justify-content-between align-items-center"):
            gui.write("Delete Workspace")

            dialog_ref = gui.use_confirm_dialog(key="delete-workspace")
            gui.button_with_confirm_dialog(
                ref=dialog_ref,
                trigger_label=f"{icons.delete} Delete",
                trigger_className="py-2 bg-danger border-danger text-light",
                modal_title="#### Delete Workspace",
                modal_content=(
                    f"Are you sure you want to delete **{membership.workspace.display_name(membership.user)}**? This action is irreversible.\n\n"
                    f"Your subscriptions will be canceled and all data will be lost."
                ),
                confirm_label="Delete",
                confirm_className="bg-danger border-danger text-light",
            )

            if dialog_ref.pressed_confirm:
                if membership.workspace.subscription:
                    membership.workspace.subscription.cancel()
                    membership.workspace.subscription.delete()
                membership.workspace.delete()
                parent_dialog.set_open(False)
                gui.rerun()


def render_workspace_leave_dialog(
    dialog_ref: gui.ConfirmDialogRef, current_member: WorkspaceMembership
) -> int | None:
    with gui.confirm_dialog(
        ref=dialog_ref,
        modal_title="#### Leave Workspace",
        confirm_label="Leave",
        confirm_className="bg-danger border-danger text-light",
    ):
        gui.write("Are you sure you want to leave this workspace?")

        if current_member.role != WorkspaceRole.OWNER:
            return
        workspace = current_member.workspace

        if workspace.memberships.count() == 1:
            gui.caption(
                "You are the only member. You will lose access to this team if you leave."
            )

        elif workspace.memberships.filter(role=WorkspaceRole.OWNER).count() == 1:
            gui.caption(
                "You are the only owner of this workspace. Please choose another member to promote to owner."
            )
            qs = (
                AppUser.objects.filter(
                    workspace_memberships__workspace=workspace,
                    workspace_memberships__deleted__isnull=True,
                )
                .exclude(id=current_member.user_id)
                .order_by("workspace_memberships__role")
            )
            choices = {user.id: user.full_name() for user in qs}
            return gui.selectbox(
                "###### New Owner",
                options=choices,
                format_func=choices.get,
            )


def render_members_list(workspace: Workspace, current_member: WorkspaceMembership):
    with gui.tag("table", className="table table-responsive"):
        with gui.tag("thead"), gui.tag("tr"):
            with gui.tag("th", scope="col"):
                gui.html("Name")
            with gui.tag("th", scope="col"):
                gui.html("Role")
            with gui.tag("th", scope="col", className="text-nowrap"):
                gui.html(f"{icons.time}&nbsp;Since")
            with gui.tag("th", scope="col"):
                gui.html("")

        with gui.tag("tbody"):
            for m in workspace.memberships.all().order_by("created_at"):
                with gui.tag("tr", className="align-middle"):
                    with gui.tag("td"):
                        name = m.user.full_name(current_user=current_member.user)
                        if m.user.handle_id:
                            with gui.link(to=m.user.handle.get_app_url()):
                                gui.html(html_lib.escape(name))
                        else:
                            gui.html(html_lib.escape(name))
                    with gui.tag("td", className="text-nowrap"):
                        gui.html(WorkspaceRole.display_html(m.role))
                    with gui.tag("td"):
                        gui.html("...", **render_local_date_attrs(m.created_at))
                    with gui.tag("td", className="text-end"):
                        render_membership_actions(m, current_member=current_member)


def render_membership_actions(
    m: WorkspaceMembership, current_member: WorkspaceMembership
):
    if current_member.can_change_role(m):
        if m.role == WorkspaceRole.MEMBER:
            ref = gui.use_confirm_dialog(key=f"promote-member-{m.pk}")
            gui.button_with_confirm_dialog(
                ref=ref,
                trigger_label=f"{icons.admin} Make Admin",
                trigger_className="btn-sm my-0 py-0",
                modal_title="#### Make an Admin",
                modal_content=f"Are you sure you want to promote **{m.user.full_name()}** to an admin?",
                confirm_label="Promote",
            )
            if ref.pressed_confirm:
                m.role = WorkspaceRole.ADMIN
                m.save(update_fields=["role"])
                gui.rerun()

        elif m.role == WorkspaceRole.ADMIN:
            ref = gui.use_confirm_dialog(key=f"demote-member-{m.pk}")
            gui.button_with_confirm_dialog(
                ref=ref,
                trigger_label=f"{icons.remove_user} Revoke Admin",
                trigger_className="btn-sm my-0 py-0",
                modal_title="#### Revoke an Admin",
                modal_content=f"Are you sure you want to revoke admin privileges from **{m.user.full_name()}**?",
                confirm_label="Revoke",
            )
            if ref.pressed_confirm:
                m.role = WorkspaceRole.MEMBER
                m.save(update_fields=["role"])
                gui.rerun()

    if current_member.can_kick(m):
        ref = gui.use_confirm_dialog(key=f"remove-member-{m.pk}")
        gui.button_with_confirm_dialog(
            ref=ref,
            trigger_label=f"{icons.remove_user} Remove",
            trigger_className="btn-sm my-0 py-0 text-danger",
            modal_title="#### Remove a Member",
            modal_content=f"Are you sure you want to remove **{m.user.full_name()}** from **{m.workspace.display_name(m.user)}**?",
            confirm_label="Remove",
            confirm_className="bg-danger border-danger text-light",
        )
        if ref.pressed_confirm:
            m.delete()
            gui.rerun()


def render_pending_invites_list(
    workspace: Workspace, *, current_member: WorkspaceMembership
):
    pending_invites = workspace.invites.filter(status=WorkspaceInvite.Status.PENDING)
    if not pending_invites:
        return

    gui.write("#### Pending")
    with gui.tag("table", className="table table-responsive"):
        with gui.tag("thead"), gui.tag("tr"):
            with gui.tag("th", scope="col"):
                gui.html("Email")
            with gui.tag("th", scope="col"):
                gui.html("Invited By")
            with gui.tag("th", scope="col", className="text-nowrap"):
                gui.html(f"{icons.time} Invite Sent")
            with gui.tag("th", scope="col"):
                pass

        with gui.tag("tbody"):
            for invite in pending_invites:
                with gui.tag("tr", className="text-break align-middle"):
                    with gui.tag("td"):
                        gui.html(html_lib.escape(invite.email))
                    with gui.tag("td"):
                        gui.html(
                            html_lib.escape(
                                invite.created_by.full_name(
                                    current_user=current_member.user
                                )
                            )
                        )
                    with gui.tag("td"):
                        last_invited_at = invite.last_email_sent_at or invite.created_at
                        gui.html(str(naturaltime(last_invited_at)))
                    with gui.tag("td", className="text-end"):
                        render_invitation_actions(invite, current_member=current_member)


def render_invitation_actions(
    invite: WorkspaceInvite, current_member: WorkspaceMembership
):
    if current_member.can_invite() and invite.can_resend_email():
        ref = gui.use_confirm_dialog(key=f"resend-invite-{invite.pk}")
        gui.button_with_confirm_dialog(
            ref=ref,
            trigger_className="btn-sm my-0 py-0",
            trigger_label=f"{icons.email} Resend",
            modal_title="#### Resend Invitation",
            modal_content=f"Resend invitation to **{invite.email}**?",
            confirm_label="Resend",
        )
        if ref.pressed_confirm:
            try:
                invite.send_email()
            except ValidationError:
                pass

    if current_member.can_invite():
        copy_to_clipboard_button(
            label=f"{icons.copy_solid} Copy Invite",
            value=invite.get_invite_url(),
            type="secondary",
            className="btn-sm my-0 py-0",
        )

        ref = gui.use_confirm_dialog(key=f"cancel-invitation-{invite.pk}")
        gui.button_with_confirm_dialog(
            ref=ref,
            trigger_label=f"{icons.cancel} Cancel",
            trigger_className="btn-sm my-0 py-0 text-danger",
            modal_title="#### Cancel Invitation",
            modal_content=f"Are you sure you want to cancel the invitation to **{invite.email}**?",
            cancel_label="No, keep it",
            confirm_label="Yes, Cancel",
            confirm_className="bg-danger border-danger text-light",
        )
        if ref.pressed_confirm:
            invite.cancel(user=current_member.user)
            gui.rerun()


def clear_workspace_create_or_edit_form():
    keys = {k for k in gui.session_state.keys() if k.startswith("workspace-")}
    for k in keys:
        gui.session_state.pop(k, None)


def render_workspace_create_or_edit_form(
    workspace: Workspace,
    current_user: AppUser,
):
    workspace.name = gui.text_input(
        "###### Team Name",
        key="workspace-name",
        value=workspace.name,
    ).strip()
    if current_user.email or workspace.domain_name:
        workspace.domain_name = gui.selectbox(
            "###### Domain Name _(Optional)_",
            options={
                workspace.domain_name,
                current_user.email and current_user.email.split("@")[-1],
            }
            | {None},
            key="workspace-domain-name",
            value=workspace.domain_name,
        )
    if workspace.domain_name:
        gui.caption(
            f"We'll automatically add any user with an `@{workspace.domain_name}` email to this workspace."
        )
    workspace.photo_url = gui.file_uploader(
        "###### Logo",
        accept=["image/*"],
        key="workspace-logo",
        value=workspace.photo_url,
    )


def left_and_right(*, className: str = "", **props):
    className += " d-flex flex-row justify-content-between align-items-center"
    with gui.div(className=className, **props):
        return gui.div(), gui.div()
