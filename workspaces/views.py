import html as html_lib
from copy import copy

from django.db import transaction
import gooey_gui as gui
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.core.exceptions import ValidationError
from django.db.models import F
from django.utils.translation import ngettext

from app_users.models import AppUser
from daras_ai_v2 import icons, settings, urls
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.fastapi_tricks import get_app_route_url, get_route_path
from daras_ai_v2.profiles import (
    render_handle_input,
    render_profile_link_buttons,
    update_handle,
)
from daras_ai_v2.user_date_widgets import render_local_date_attrs
from payments.plans import PricingPlan
from .models import (
    Workspace,
    WorkspaceInvite,
    WorkspaceMembership,
    WorkspaceRole,
)
from .widgets import (
    get_current_workspace,
    get_workspace_domain_name_options,
    set_current_workspace,
)

rounded_border = "w-100 border shadow-sm rounded py-4 px-3"


def invitation_page(
    current_user: AppUser | None, session: dict, invite: WorkspaceInvite
):
    from routers.root import login
    from routers.account import members_route

    if invite.status == WorkspaceInvite.Status.ACCEPTED:
        set_current_workspace(session, int(invite.workspace_id))
        raise gui.RedirectException(get_route_path(members_route))

    WorkspaceInvite.objects.filter(id=invite.id).update(clicks=F("clicks") + 1)

    with (
        gui.div(
            className="position-absolute top-0 start-0 bottom-0 bg-black min-vw-100 min-vh-100",
            style={"overflow-x": "hidden"},
        ),
        gui.center(className="mb-5"),
    ):
        gui.image(
            src=settings.GOOEY_LOGO_IMG_WHITE,
            className="my-2",
            style={
                "width": "min(400px, 75vw)",
                "height": "auto",
                "objectFit": "cover",
                "aspectRatio": "8/3",
            },
        )
        with gui.div(
            className="d-flex flex-column justify-content-center align-items-center bg-white p-5 rounded-3",
            style={"width": "min(500px, 90vw)"},
        ):
            if invite.status != WorkspaceInvite.Status.PENDING:
                gui.write(
                    f"This invitation has been {invite.get_status_display().lower()}.",
                    className="mt-4 d-block",
                )
                return

            gui.image(
                src=invite.created_by.photo_url,
                className="rounded-circle m-0",
                style={"width": "150px", "height": "150px", "objectFit": "cover"},
            )

            invite_creator = invite.created_by.full_name()
            if invite.created_by.email:
                invite_creator += f" ({invite.created_by.email})"
            gui.write(
                f"{invite_creator} has invited you to join",
                className="d-block text-muted mt-4",
            )
            with gui.div(
                className="d-block d-md-flex align-items-center justify-content-center mb-4"
            ):
                gui.image(
                    src=invite.workspace.get_photo(),
                    className="rounded",
                    style={"height": "70px", "width": "70px", "objectFit": "contain"},
                )
                with gui.tag("h1", className="my-0 ms-md-2 text-center text-md-start"):
                    gui.html(html_lib.escape(invite.workspace.display_name()))

            members_count = invite.workspace.memberships.count()
            members_text = ngettext("member", "members", members_count)
            gui.caption(f"{members_count} {members_text}")

            if not current_user or current_user.is_anonymous:
                login_url = get_app_route_url(
                    login, query_params={"next": invite.get_invite_url()}
                )
                with gui.tag(
                    "a",
                    className="my-2 w-100 btn btn-theme btn-primary",
                    href=login_url,
                ):
                    gui.html("Join Workspace")
                return

            if gui.button(
                "Join Workspace",
                className="my-2 w-100",
                type="primary",
                style={"max-width": "400px"},
            ):
                with gui.div(className="text-start"):
                    # reset text alignment from center
                    _handle_invite_accepted(
                        invite, session=session, current_user=current_user
                    )


def _handle_invite_accepted(
    invite: WorkspaceInvite, session: dict, current_user: AppUser | None
):
    from routers.account import account_route
    from routers.root import login, logout

    workspace_redirect_url = get_route_path(account_route)

    if not current_user.email or invite.email.lower() != current_user.email.lower():
        # logout current user, and redirect to login
        login_url = get_app_route_url(
            login, query_params={"next": invite.get_invite_url()}
        )
        logout_url = get_app_route_url(logout, query_params={"next": login_url})
        gui.error(
            f"""
            Doh! This invitation is for `{invite.email}`, and you \
            are logged in with `{current_user.email}`.
            Please have the workspace owner invite `{current_user.email}` \
            or [login to Gooey.AI]({logout_url}) with `{invite.email}`.
            """,
        )
        return

    invite.accept(current_user, updated_by=current_user)
    set_current_workspace(session, int(invite.workspace_id))
    raise gui.RedirectException(workspace_redirect_url)


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

    with gui.div(className="mt-3 d-block d-sm-flex justify-content-between"):
        col1 = gui.div(
            className="d-block d-md-flex text-center text-sm-start align-items-start"
        )
        col2 = gui.div()

    with col1:
        gui.image(
            workspace.get_photo(),
            className="my-0 me-4 rounded",
            style={"width": "128px", "height": "128px", "objectFit": "contain"},
        )
        with gui.div(className="d-flex flex-column justify-content-start"):
            plan = (
                workspace.subscription
                and PricingPlan.from_sub(workspace.subscription)
                or PricingPlan.STARTER
            )

            with gui.tag("h1", className="my-0"):
                gui.html(html_lib.escape(workspace.display_name(membership.user)))
            if workspace.domain_name:
                gui.write(
                    f"Domain: `@{workspace.domain_name}`",
                    className="container-margin-reset text-muted",
                )

            if workspace.description:
                gui.write(workspace.description, className="container-margin-reset")

            with gui.div(className="mt-2"):
                if workspace.handle:
                    with gui.div(className="d-flex align-items-baseline gap-3"):
                        pretty_handle_url = urls.remove_scheme(
                            workspace.handle.get_app_url().rstrip("/")
                        )
                        gui.write(pretty_handle_url, className="container-margin-reset")
                        render_profile_link_buttons(workspace.handle)

                with gui.div(className="d-flex gap-3"):
                    gui.html(
                        f'<div><span class="text-muted">Credits:</span> {workspace.balance}</div>'
                    )
                    gui.html(
                        f'<div><span class="text-muted">Plan:</span> {plan.title}</div>'
                    )
                    if membership.can_edit_workspace() and plan in (
                        PricingPlan.STARTER,
                        PricingPlan.CREATOR,
                    ):
                        gui.html(
                            f'<a class="link-primary" href="{get_route_path(account_route)}">Upgrade</a>'
                        )

    if membership.can_edit_workspace():
        with col2, gui.div(className="text-center"):
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
    from routers.workspace import validate_and_invite_from_emails_csv

    if not membership.can_invite():
        return

    ref = gui.use_confirm_dialog(key="invite-members", close_on_confirm=False)

    if gui.button(label=f"{icons.add_user} Invite", **props):
        clear_invite_creation_form()
        ref.set_open(True)
    if not ref.is_open:
        return

    with gui.confirm_dialog(
        ref=ref,
        modal_title="#### Invite Members",
        confirm_label=f"{icons.send} Send",
    ):
        role, emails_csv = render_invite_creation_form(membership.workspace)
        if not ref.pressed_confirm:
            return

        error_msg_container = gui.div()
        success = validate_and_invite_from_emails_csv(
            emails_csv,
            role=WorkspaceRole(role),
            workspace=membership.workspace,
            current_user=membership.user,
            error_msg_container=error_msg_container,
            max_emails=5,
        )
        if not success:
            # don't close
            return

        if close_on_confirm:
            ref.set_open(False)
            gui.rerun()
        else:
            gui.success("Invites sent!")


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
        input_handle_name = gui.session_state.pop(
            "workspace-handle-name",
            workspace_copy.handle and workspace_copy.handle.name,
        )

        if not ref.pressed_confirm:
            return
        try:
            workspace_copy.full_clean()
            with transaction.atomic():
                new_handle = update_handle(workspace_copy.handle, input_handle_name)
                if new_handle != workspace_copy.handle:
                    workspace_copy.handle = new_handle
                workspace_copy.save()
        except ValidationError as e:
            # newlines in markdown
            gui.write("\n".join(e.messages), className="text-danger")
        else:
            membership.workspace.refresh_from_db()
            ref.set_open(False)
            gui.rerun()


def render_workspace_edit_view_by_membership(
    dialog_ref: gui.ConfirmDialogRef, membership: WorkspaceMembership
):
    workspace = copy(membership.workspace)
    render_workspace_edit_form(workspace, membership.user)
    render_danger_zone_by_membership(dialog_ref, membership)
    return workspace


def clear_invite_creation_form():
    keys = {k for k in gui.session_state.keys() if k.startswith("invite-form-")}
    for k in keys:
        gui.session_state.pop(k, None)


def render_invite_creation_form(workspace: Workspace) -> tuple[str, str]:
    from routers.workspace import render_emails_csv_input

    gui.write(f"Invite to **{workspace.display_name()}**.")

    emails_csv = render_emails_csv_input(key="invite-form-emails", max_emails=5)

    role = gui.selectbox(
        "###### Role",
        options=WorkspaceRole,
        format_func=WorkspaceRole.display_html,
        value=WorkspaceRole.MEMBER.value,
        key="invite-form-role",
    )

    if workspace.domain_name:
        gui.caption(
            f"Users with `@{workspace.domain_name}` email will be added automatically."
        )

    return role, emails_csv


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
    with gui.div(className="table-responsive"), gui.tag("table", className="table"):
        with gui.tag("thead"), gui.tag("tr"):
            with gui.tag("th", scope="col"):
                gui.html("Name")
            with gui.tag("th", scope="col"):
                gui.html("Role")
            with gui.tag("th", scope="col", className="text-nowrap"):
                gui.html(f"{icons.time} Since")
            with gui.tag("th", scope="col"):
                gui.html("")

        with gui.tag("tbody"):
            for m in workspace.memberships.all().order_by("created_at"):
                with gui.tag("tr", className="align-middle"):
                    with gui.tag("td"):
                        name = m.user.full_name(current_user=current_member.user)
                        if handle := m.user.get_handle():
                            with gui.link(to=handle.get_app_url()):
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
    with gui.div(className="table-responsive"), gui.tag("table", className="table"):
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
                with gui.tag("tr", className="align-middle"):
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


def render_workspace_edit_form(
    workspace: Workspace,
    current_user: AppUser,
):
    workspace.name = gui.text_input(
        "###### Team Name",
        key="workspace-name",
        value=workspace.name,
    ).strip()
    render_handle_input(
        "###### Handle",
        key="workspace-handle-name",
        handle=workspace.handle,
    )
    workspace.description = gui.text_area(
        "###### Description _(Optional)_",
        key="workspace-description",
        placeholder="Tell the world about your team!",
        value=workspace.description,
    )

    domain_name_options = get_workspace_domain_name_options(
        workspace=workspace, current_user=current_user
    )
    if domain_name_options:
        workspace.domain_name = gui.selectbox(
            "###### Domain Name _(Optional)_",
            options=domain_name_options,
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
    workspace.banner_url = gui.file_uploader(
        "###### Banner",
        accept=["image/*"],
        key="workspace-banner-url",
        value=workspace.banner_url,
    )


def left_and_right(*, className: str = "", **props):
    className += " d-flex flex-row justify-content-between align-items-center"
    with gui.div(className=className, **props):
        return gui.div(), gui.div()
