import html as html_lib
from django.core.exceptions import ValidationError
from django.db import transaction

import gooey_ui as st
from app_users.models import AppUser
from gooey_ui.components.modal import Modal
from orgs.models import Org, OrgInvitation, OrgMembership, OrgRole
from daras_ai_v2 import icons


DEFAULT_ORG_LOGO = "https://seccdn.libravatar.org/avatar/40f8d096a3777232204cb3f796c577b7?s=80&forcedefault=y&default=monsterid"


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

    with st.div(className="d-flex justify-content-between"):
        with st.div(className="d-flex align-items-center"):
            st.image(
                org.logo or DEFAULT_ORG_LOGO,
                className="my-0 me-2",
                style={"width": "128px", "height": "128px", "object-fit": "contain"},
            )
            st.write(f"# {org.name}")

        if membership.can_edit_org_metadata():
            org_edit_modal = Modal("Edit Org", key="edit-org-modal")
            if org_edit_modal.is_open():
                with org_edit_modal.container():
                    render_org_edit_view(membership.org, modal=org_edit_modal)

            with st.div(className="d-flex align-items-center"):
                if st.button(f"{icons.edit} Edit", className="btn btn-theme"):
                    org_edit_modal.open()

    with st.div(className="mt-4"):
        with st.div(className="d-flex justify-content-between align-items-center"):
            st.write("## Members")

            if membership.can_invite():
                invite_modal = Modal("Invite Member", key="invite-member-modal")
                if st.button(f"{icons.add_user} Invite Member", type="primary"):
                    invite_modal.open()

                if invite_modal.is_open():
                    with invite_modal.container():
                        render_invite_creation_view(
                            org=org, inviter=current_user, modal=invite_modal
                        )

        render_members_list(org=org, current_membership=membership)

    with st.div(className="mt-4"):
        render_pending_invitations_list(org=org, current_user=current_user)

    with st.div(className="mt-4"):
        st.write("# Danger Zone")

        if membership.role == OrgRole.OWNER:
            # Owner can't leave! Only delete
            if st.button(
                "Delete Org",
                className="btn btn-theme bg-danger border-danger text-white",
            ):
                org.soft_delete()
                st.experimental_rerun()
        else:
            if st.button(
                "Leave Org",
                className="btn btn-theme bg-danger border-danger text-white",
            ):
                org.members.remove(current_user)
                st.experimental_rerun()


def render_org_creation_view(user: AppUser):
    st.write(f"# {icons.company} Create an Org", unsafe_allow_html=True)
    name = st.text_input("Team Name")
    logo = st.file_uploader("Org Logo", accept=["image/*"])

    if st.button("Create"):
        Org.objects.create_org(created_by=user, name=name, logo=logo)
        st.experimental_rerun()


def render_org_edit_view(org: Org, *, modal: Modal):
    org.name = st.text_input("Org Name", value=org.name)
    org.logo = st.file_uploader("Org Logo", accept=["image/*"], value=org.logo)

    if st.button("Save"):
        try:
            org.full_clean()
        except ValidationError as e:
            # newlines in markdown
            st.write("  \n".join(e.messages), className="text-danger")
        else:
            org.save()
            modal.close()


def render_members_list(org: Org, current_membership: OrgMembership):
    with st.raw_table(["Name", "Role", f"{icons.time} Since", ""]):
        for m in org.memberships.all().order_by("created_at"):
            name_val = m.user.display_name or m.user.first_name()
            if current_membership == m:
                name_val += " (You)"
            with st.tag("tr"):
                with st.tag("td"):
                    if m.user.handle_id:
                        with st.link(to=m.user.handle.get_app_url()):
                            st.html(html_lib.escape(name_val))
                    else:
                        st.html(html_lib.escape(name_val))
                with st.tag("td"):
                    st.html(html_lib.escape(m.get_role_display()))
                with st.tag("td"):
                    st.html(m.created_at.strftime("%b %d, %Y"))
                with st.tag("td", className="text-end"):
                    render_role_change_buttons(m, current_membership=current_membership)
                    render_membership_buttons(m, current_membership=current_membership)


def render_role_change_buttons(m: OrgMembership, current_membership: OrgMembership):
    if current_membership.can_change_role(m):
        if m.role == OrgRole.MEMBER:
            if st.button(
                f"{icons.admin} Make Admin",
                className="btn btn-theme btn-sm my-0 py-0",
                unsafe_allow_html=True,
            ):
                m.role = OrgRole.ADMIN
                m.save()
                st.experimental_rerun()
        if m.role == OrgRole.ADMIN:
            if st.button(
                f"{icons.admin} Remove Admin",
                className="btn btn-theme btn-sm my-0 py-0",
                unsafe_allow_html=True,
            ):
                m.role = OrgRole.MEMBER
                m.save()
                st.experimental_rerun()

    if current_membership.can_transfer_ownership(m):
        if st.button(
            f"{icons.transfer_ownership} Transfer Ownership",
            className="btn btn-theme btn-sm my-0 py-0 bg-danger border-danger text-light",
            unsafe_allow_html=True,
        ):
            m.role = OrgRole.OWNER
            current_membership.role = OrgRole.ADMIN
            with transaction.atomic():
                m.save()
                current_membership.save()
            st.experimental_rerun()


def render_membership_buttons(m: OrgMembership, current_membership: OrgMembership):
    if current_membership.can_kick(m):
        if st.button(
            f"{icons.remove_user} Remove",
            className="btn btn-theme btn-sm my-0 py-0 bg-danger border-danger text-light",
            unsafe_allow_html=True,
        ):
            # TODO: soft-delete
            m.delete()
            st.experimental_rerun()


def render_pending_invitations_list(org: Org, current_user: AppUser):
    pending_invitations = org.invitations.filter(status=OrgInvitation.Status.PENDING)
    if not pending_invitations:
        return

    st.write("## Pending")
    table = st.raw_table(["Email", "Invited By", f"{icons.time} Invited on"])
    with table:
        for invite in pending_invitations:
            inviter_name = invite.inviter.display_name or invite.inviter.first_name()
            if current_user == invite.inviter:
                inviter_name += " (You)"
            st.table_row(
                [
                    invite.invitee_email,
                    inviter_name,
                    invite.created_at.strftime("%b %d, %Y"),
                ]
            )


def render_invite_creation_view(org: Org, inviter: AppUser, modal: Modal):
    email = st.text_input("Email")

    if st.button(f"{icons.add_user} Invite", type="primary", unsafe_allow_html=True):
        try:
            org.invite_user(invitee_email=email, inviter=inviter, role=OrgRole.MEMBER)
            modal.close()
        except ValidationError as e:
            st.write(", ".join(e.messages), className="text-danger")
