from __future__ import annotations

import html as html_lib

import gooey_gui as gui
from django.core.exceptions import ValidationError

from app_users.models import AppUser
from orgs.models import Org, OrgInvitation, OrgMembership, OrgRole
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_route_path


DEFAULT_ORG_LOGO = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/74a37c52-8260-11ee-a297-02420a0001ee/gooey.ai%20-%20A%20pop%20art%20illustration%20of%20robots%20taki...y%20Liechtenstein%20mint%20colour%20is%20main%20city%20Seattle.png"


def invitation_page(user: AppUser, invitation: OrgInvitation):
    from routers.account import orgs_route

    orgs_page_path = get_route_path(orgs_route)

    with st.div(className="text-center my-5"):
        st.write(
            f"# Invitation to join {invitation.org.name}", className="d-block mb-5"
        )

        if invitation.org.memberships.filter(user=user).exists():
            # redirect to org page
            raise st.RedirectException(orgs_page_path)

        if invitation.status != OrgInvitation.Status.PENDING:
            st.write(f"This invitation has been {invitation.get_status_display()}.")
            return

        st.write(
            f"**{format_user_name(invitation.inviter)}** has invited you to join **{invitation.org.name}**."
        )

        if other_m := user.org_memberships.first():
            st.caption(
                f"You are currently a member of [{other_m.org.name}]({orgs_page_path}). You will be removed from that team if you accept this invitation."
            )
            accept_label = "Leave and Accept"
        else:
            accept_label = "Accept"

        with st.div(
            className="d-flex justify-content-center align-items-center mx-auto",
            style={"max-width": "600px"},
        ):
            accept_button = st.button(accept_label, type="primary", className="w-50")
            reject_button = st.button("Decline", type="secondary", className="w-50")

        if accept_button:
            invitation.accept(user=user)
            raise st.RedirectException(orgs_page_path)
        if reject_button:
            invitation.reject(user=user)


def orgs_page(user: AppUser):
    memberships = user.org_memberships.all()
    if not memberships:
        st.write("*You're not part of an organization yet... Create one?*")

        render_org_creation_view(user)
    else:
        # only support one org for now
        render_org_by_membership(memberships.first())


def render_org_by_membership(membership: OrgMembership):
    """
    membership object has all the information we need:
        - org
        - current user
        - current user's role in the org (and other metadata)
    """
    org = membership.org
    current_user = membership.user

    with st.div(
        className="d-xs-block d-sm-flex flex-row-reverse justify-content-between"
    ):
        with st.div(className="d-flex justify-content-center align-items-center"):
            if membership.can_edit_org_metadata():
                org_edit_modal = gui.Modal("Edit Org", key="edit-org-modal")
                if org_edit_modal.is_open():
                    with org_edit_modal.container():
                        render_org_edit_view_by_membership(
                            membership, modal=org_edit_modal
                        )

                if st.button(f"{icons.edit} Edit", type="secondary"):
                    org_edit_modal.open()

        with st.div(className="d-flex align-items-center"):
            st.image(
                org.logo or DEFAULT_ORG_LOGO,
                className="my-0 me-4 rounded",
                style={"width": "128px", "height": "128px", "object-fit": "contain"},
            )
            with st.div(className="d-flex flex-column justify-content-center"):
                st.write(f"# {org.name}")
                if org.domain_name:
                    st.write(
                        f"Org Domain: `@{org.domain_name}`", className="text-muted"
                    )

    with st.div(className="mt-4"):
        with st.div(className="d-flex justify-content-between align-items-center"):
            st.write("## Members")

            if membership.can_invite():
                invite_modal = gui.Modal("Invite Member", key="invite-member-modal")
                if st.button(f"{icons.add_user} Invite"):
                    invite_modal.open()

                if invite_modal.is_open():
                    with invite_modal.container():
                        render_invite_creation_view(
                            org=org, inviter=current_user, modal=invite_modal
                        )

        render_members_list(org=org, current_member=membership)

    with st.div(className="mt-4"):
        render_pending_invitations_list(org=org, current_member=membership)

    with st.div(className="mt-4"):
        org_leave_modal = gui.Modal("Leave Org", key="leave-org-modal")
        if org_leave_modal.is_open():
            with org_leave_modal.container():
                render_org_leave_view_by_membership(membership, modal=org_leave_modal)

        with st.div(className="text-end"):
            leave_org = st.button(
                "Leave",
                className="btn btn-theme bg-danger border-danger text-white",
            )
        if leave_org:
            org_leave_modal.open()


def render_org_creation_view(user: AppUser):
    st.write(f"# {icons.company} Create an Org", unsafe_allow_html=True)
    org_fields = render_org_create_or_edit_form()

    if st.button("Create"):
        try:
            Org.objects.create_org(
                created_by=user,
                **org_fields,
            )
        except ValidationError as e:
            st.write(", ".join(e.messages), className="text-danger")
        else:
            st.experimental_rerun()


def render_org_edit_view_by_membership(membership: OrgMembership, *, modal: gui.Modal):
    org = membership.org
    render_org_create_or_edit_form(org=org)

    if st.button("Save", className="w-100", type="primary"):
        try:
            org.full_clean()
        except ValidationError as e:
            # newlines in markdown
            st.write("  \n".join(e.messages), className="text-danger")
        else:
            org.save()
            modal.close()

    if membership.can_delete_org() or membership.can_transfer_ownership():
        st.write("---")
        render_danger_zone_by_membership(membership)


def render_danger_zone_by_membership(membership: OrgMembership):
    st.write("### Danger Zone", className="d-block my-2")

    if membership.can_delete_org():
        org_deletion_modal = gui.Modal("Delete Organization", key="delete-org-modal")
        if org_deletion_modal.is_open():
            with org_deletion_modal.container():
                render_org_deletion_view_by_membership(
                    membership, modal=org_deletion_modal
                )

        with st.div(className="d-flex justify-content-between align-items-center"):
            st.write("Delete Organization")
            if st.button(
                f"{icons.delete} Delete",
                className="btn btn-theme py-2 bg-danger border-danger text-white",
            ):
                org_deletion_modal.open()


def render_org_deletion_view_by_membership(
    membership: OrgMembership, *, modal: gui.Modal
):
    st.write(
        f"Are you sure you want to delete **{membership.org.name}**? This action is irreversible."
    )

    with st.div(className="d-flex"):
        if st.button(
            "Cancel", type="secondary", className="border-danger text-danger w-50"
        ):
            modal.close()

        if st.button(
            "Delete", className="btn btn-theme bg-danger border-danger text-light w-50"
        ):
            membership.org.delete()
            modal.close()


def render_org_leave_view_by_membership(
    current_member: OrgMembership, *, modal: gui.Modal
):
    org = current_member.org

    st.write("Are you sure you want to leave this organization?")

    new_owner = None
    if current_member.role == OrgRole.OWNER and org.memberships.count() == 1:
        st.caption(
            "You are the only member. You will lose access to this team if you leave."
        )
    elif (
        current_member.role == OrgRole.OWNER
        and org.memberships.filter(role=OrgRole.OWNER).count() == 1
    ):
        members_by_uid = {
            m.user.uid: m
            for m in org.memberships.all().select_related("user")
            if m != current_member
        }

        st.caption(
            "You are the only owner of this organization. Please choose another member to promote to owner."
        )
        new_owner_uid = st.selectbox(
            "New Owner",
            options=list(members_by_uid),
            format_func=lambda uid: format_user_name(members_by_uid[uid].user),
        )
        new_owner = members_by_uid[new_owner_uid]

    with st.div(className="d-flex"):
        if st.button(
            "Cancel", type="secondary", className="border-danger text-danger w-50"
        ):
            modal.close()

        if st.button(
            "Leave", className="btn btn-theme bg-danger border-danger text-light w-50"
        ):
            if new_owner:
                new_owner.role = OrgRole.OWNER
                new_owner.save()
            current_member.delete()
            modal.close()


def render_members_list(org: Org, current_member: OrgMembership):
    with st.tag("table", className="table table-responsive"):
        with st.tag("thead"), st.tag("tr"):
            with st.tag("th", scope="col"):
                st.html("Name")
            with st.tag("th", scope="col"):
                st.html("Role")
            with st.tag("th", scope="col"):
                st.html(f"{icons.time} Since")
            with st.tag("th", scope="col"):
                st.html("")

        with st.tag("tbody"):
            for m in org.memberships.all().order_by("created_at"):
                with st.tag("tr"):
                    with st.tag("td"):
                        name = format_user_name(
                            m.user, current_user=current_member.user
                        )
                        if m.user.handle_id:
                            with st.link(to=m.user.handle.get_app_url()):
                                st.html(html_lib.escape(name))
                        else:
                            st.html(html_lib.escape(name))
                    with st.tag("td"):
                        st.html(m.get_role_display())
                    with st.tag("td"):
                        st.html(m.created_at.strftime("%b %d, %Y"))
                    with st.tag("td", className="text-end"):
                        render_membership_actions(m, current_member=current_member)


def render_membership_actions(m: OrgMembership, current_member: OrgMembership):
    if current_member.can_change_role(m):
        if m.role == OrgRole.MEMBER:
            modal, confirmed = button_with_confirmation_modal(
                f"{icons.admin} Make Admin",
                key=f"promote-member-{m.pk}",
                unsafe_allow_html=True,
                confirmation_text=f"Are you sure you want to promote **{format_user_name(m.user)}** to an admin?",
                modal_title="Make Admin",
                modal_key=f"promote-member-{m.pk}-modal",
            )
            if confirmed:
                m.role = OrgRole.ADMIN
                m.save()
                modal.close()
        elif m.role == OrgRole.ADMIN:
            modal, confirmed = button_with_confirmation_modal(
                f"{icons.remove_user} Revoke Admin",
                key=f"demote-member-{m.pk}",
                unsafe_allow_html=True,
                confirmation_text=f"Are you sure you want to revoke admin privileges from **{format_user_name(m.user)}**?",
                modal_title="Revoke Admin",
                modal_key=f"demote-member-{m.pk}-modal",
            )
            if confirmed:
                m.role = OrgRole.MEMBER
                m.save()
                modal.close()

    if current_member.can_kick(m):
        modal, confirmed = button_with_confirmation_modal(
            f"{icons.remove_user} Remove",
            key=f"remove-member-{m.pk}",
            unsafe_allow_html=True,
            confirmation_text=f"Are you sure you want to remove **{format_user_name(m.user)}** from **{m.org.name}**?",
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
    if st.button(btn_label, className=btn_classes, **btn_props):
        modal.open()

    if modal.is_open():
        with modal.container(className=modal_className):
            st.write(confirmation_text)
            with st.div(className="d-flex"):
                if st.button(
                    "Cancel",
                    type="secondary",
                    className="border-danger text-danger w-50",
                ):
                    modal.close()

                confirmed = st.button(
                    "Confirm",
                    className="btn btn-theme bg-danger border-danger text-light w-50",
                )
                return modal, confirmed

    return modal, False


def render_pending_invitations_list(org: Org, *, current_member: OrgMembership):
    pending_invitations = org.invitations.filter(status=OrgInvitation.Status.PENDING)
    if not pending_invitations:
        return

    st.write("## Pending")
    with st.tag("table", className="table table-responsive"):
        with st.tag("thead"), st.tag("tr"):
            with st.tag("th", scope="col"):
                st.html("Email")
            with st.tag("th", scope="col"):
                st.html("Invited By")
            with st.tag("th", scope="col"):
                st.html(f"{icons.time} Last invited on")
            with st.tag("th", scope="col"):
                pass

        with st.tag("tbody"):
            for invite in pending_invitations:
                with st.tag("tr", className="text-break"):
                    with st.tag("td"):
                        st.html(html_lib.escape(invite.invitee_email))
                    with st.tag("td"):
                        st.html(
                            html_lib.escape(
                                format_user_name(
                                    invite.inviter, current_user=current_member.user
                                )
                            )
                        )
                    with st.tag("td"):
                        last_invited_at = invite.last_email_sent_at or invite.created_at
                        st.html(last_invited_at.strftime("%b %d, %Y"))
                    with st.tag("td", className="text-end"):
                        render_invitation_actions(invite, current_member=current_member)


def render_invitation_actions(invitation: OrgInvitation, current_member: OrgMembership):
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


def render_invite_creation_view(org: Org, inviter: AppUser, modal: gui.Modal):
    email = st.text_input("Email")
    if org.domain_name:
        st.caption(
            f"Users with `@{org.domain_name}` email will be added automatically."
        )

    if st.button(f"{icons.add_user} Invite", type="primary", unsafe_allow_html=True):
        try:
            org.invite_user(
                invitee_email=email,
                inviter=inviter,
                role=OrgRole.MEMBER,
                auto_accept=org.domain_name.lower() == email.split("@")[1].lower(),
            )
        except ValidationError as e:
            st.write(", ".join(e.messages), className="text-danger")
        else:
            modal.close()


def render_org_create_or_edit_form(org: Org | None = None) -> AttrDict | Org:
    org_proxy = org or AttrDict()

    org_proxy.name = st.text_input("Team Name", value=org and org.name or "")
    org_proxy.logo = st.file_uploader(
        "Logo", accept=["image/*"], value=org and org.logo or ""
    )
    org_proxy.domain_name = st.text_input(
        "Domain Name (Optional)",
        placeholder="e.g. gooey.ai",
        value=org and org.domain_name or "",
    )
    if org_proxy.domain_name:
        st.caption(
            f"Invite any user with `@{org_proxy.domain_name}` email to this organization."
        )

    return org_proxy


def format_user_name(user: AppUser, current_user: AppUser | None = None):
    name = user.display_name or user.first_name()
    if current_user and user == current_user:
        name += " (You)"
    return name


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self
