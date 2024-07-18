import html as html_lib
from django.core.exceptions import ValidationError

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

    with st.div(
        className="d-xs-block d-sm-flex flex-row-reverse justify-content-between"
    ):
        with st.div(className="d-flex justify-content-center align-items-center"):
            if membership.can_edit_org_metadata():
                org_edit_modal = Modal("Edit Org", key="edit-org-modal")
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
                className="my-0 me-2",
                style={"width": "128px", "height": "128px", "object-fit": "contain"},
            )
            with st.div(className="d-flex flex-column justify-content-center"):
                st.write(f"# {org.name}")
                if org.domain_name:
                    st.write(f"Domain: `@{org.domain_name}`", className="text-muted")

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
        org_leave_modal = Modal("Leave Org", key="leave-org-modal")
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


#     if membership.can_transfer_ownership():
#         transfer_ownership_modal = Modal("Transfer Ownership", key="transfer-ownership")
#         if transfer_ownership_modal.is_open():
#             with transfer_ownership_modal.container():
#                 render_transfer_ownership_view_by_membership(
#                     membership, modal=transfer_ownership_modal
#                 )
#
#         with st.div(className="d-flex justify-content-between align-items-center"):
#             st.write("Transfer Ownership")
#             if st.button(
#                 f"{icons.transfer} Transfer",
#                 className="btn btn-theme py-2 bg-danger border-danger text-light",
#                 unsafe_allow_html=True,
#             ):
#                 transfer_ownership_modal.open()
#


def render_org_creation_view(user: AppUser):
    st.write(f"# {icons.company} Create an Org", unsafe_allow_html=True)
    name = st.text_input("Team Name")
    logo = st.file_uploader("Logo", accept=["image/*"])
    domain_name = st.text_input("Domain Name (Optional)", placeholder="e.g. gooey.ai")
    if domain_name:
        st.caption(f"Add any user with `@{domain_name}` email to this organization.")

    if st.button("Create"):
        try:
            Org.objects.create_org(
                created_by=user, name=name, logo=logo, domain_name=domain_name
            )
        except ValidationError as e:
            st.write(", ".join(e.messages), className="text-danger")
        else:
            st.experimental_rerun()


def render_org_edit_view_by_membership(membership: OrgMembership, *, modal: Modal):
    org = membership.org

    org.name = st.text_input("Team Name", value=org.name)
    org.logo = st.file_uploader("Logo", accept=["image/*"], value=org.logo)
    org.domain_name = st.text_input(
        "Domain Name (Optional)", placeholder="e.g. gooey.ai", value=org.domain_name
    )
    if org.domain_name:
        st.caption(
            f"Add any user with `@{org.domain_name}` email to this organization."
        )

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
        org_deletion_modal = Modal("Delete Organization", key="delete-org-modal")
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


def render_org_deletion_view_by_membership(membership: OrgMembership, *, modal: Modal):
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
    current_membership: OrgMembership, *, modal: Modal
):
    org = current_membership.org

    st.write("Are you sure you want to leave this organization?")

    new_owner = None
    if current_membership.role == OrgRole.OWNER and org.memberships.count() == 1:
        st.caption(
            "You are the only member. You will lose access to this team if you leave."
        )
    elif (
        current_membership.role == OrgRole.OWNER
        and org.memberships.filter(role=OrgRole.OWNER).count() == 1
    ):
        members_by_uid = {
            m.user.uid: m
            for m in org.memberships.all().select_related("user")
            if m != current_membership
        }
        new_owner_uid = st.selectbox(
            "New Owner",
            options=list(members_by_uid),
            format_func=lambda uid: format_user_name(members_by_uid[uid].user),
        )
        new_owner = members_by_uid[new_owner_uid]
        st.caption(
            "You are the only owner of this organization. Please choose another member to promote to owner."
        )

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
            org.members.remove(current_membership.user)
            modal.close()


def render_members_list(org: Org, current_membership: OrgMembership):
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
                            m.user, current_user=current_membership.user
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
                        render_membership_actions(
                            m, current_membership=current_membership
                        )


def render_membership_actions(m: OrgMembership, current_membership: OrgMembership):
    if current_membership.can_kick(m):
        member_deletion_modal = Modal(
            "Remove Member", key=f"remove-member-{m.pk}-modal"
        )
        if member_deletion_modal.is_open():
            with member_deletion_modal.container():
                render_member_deletion_view(m, modal=member_deletion_modal)

        if st.button(
            f"{icons.remove_user} Remove",
            className="btn btn-theme btn-sm my-0 py-0 bg-danger border-danger text-light",
            unsafe_allow_html=True,
        ):
            member_deletion_modal.open()


def render_member_deletion_view(membership: OrgMembership, modal: Modal):
    st.write(
        f"Are you sure you want to remove **{format_user_name(membership.user)}** from **{membership.org.name}**?"
    )

    with st.div(className="d-flex"):
        if st.button(
            "Cancel", type="secondary", className="border-danger text-danger w-50"
        ):
            modal.close()

        if st.button(
            "Remove", className="btn btn-theme bg-danger border-danger text-light w-50"
        ):
            membership.delete()
            modal.close()


def render_pending_invitations_list(org: Org, current_user: AppUser):
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
                st.html(f"{icons.time} Invited on")

        with st.tag("tbody"):
            for invite in pending_invitations:
                with st.tag("tr", className="text-break"):
                    with st.tag("td"):
                        st.html(html_lib.escape(invite.invitee_email))
                    with st.tag("td"):
                        st.html(
                            html_lib.escape(
                                format_user_name(
                                    invite.inviter, current_user=current_user
                                )
                            )
                        )
                    with st.tag("td"):
                        st.html(invite.created_at.strftime("%b %d, %Y"))


def render_invite_creation_view(org: Org, inviter: AppUser, modal: Modal):
    email = st.text_input("Email")

    if st.button(f"{icons.add_user} Invite", type="primary", unsafe_allow_html=True):
        try:
            org.invite_user(invitee_email=email, inviter=inviter, role=OrgRole.MEMBER)
        except ValidationError as e:
            st.write(", ".join(e.messages), className="text-danger")
        else:
            modal.close()


def format_user_name(user: AppUser, current_user: AppUser | None = None):
    name = user.display_name or user.first_name()
    if current_user and user == current_user:
        name += " (You)"
    return name
