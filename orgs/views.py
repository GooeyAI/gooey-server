from __future__ import annotations

import html as html_lib

import stripe
import gooey_gui as gui
from django.core.exceptions import ValidationError

from app_users.models import AppUser, PaymentProvider
from daras_ai_v2.billing import format_card_brand, payment_provider_radio
from daras_ai_v2.grid_layout_widget import grid_layout
from orgs.models import Org, OrgInvitation, OrgMembership, OrgRole
from daras_ai_v2 import icons, settings
from daras_ai_v2.fastapi_tricks import get_route_path, get_app_route_url
from daras_ai_v2.settings import templates
from daras_ai_v2.user_date_widgets import render_local_date_attrs
from payments.models import PaymentMethodSummary
from payments.plans import PricingPlan
from scripts.migrate_existing_subscriptions import available_subscriptions


DEFAULT_ORG_LOGO = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/74a37c52-8260-11ee-a297-02420a0001ee/gooey.ai%20-%20A%20pop%20art%20illustration%20of%20robots%20taki...y%20Liechtenstein%20mint%20colour%20is%20main%20city%20Seattle.png"


rounded_border = "w-100 border shadow-sm rounded py-4 px-3"


def invitation_page(user: AppUser, invitation: OrgInvitation):
    from routers.account import orgs_route

    orgs_page_path = get_route_path(orgs_route)

    with gui.div(className="text-center my-5"):
        gui.write(
            f"# Invitation to join {invitation.org.name}", className="d-block mb-5"
        )

        if invitation.org.memberships.filter(user=user).exists():
            # redirect to org page
            raise gui.RedirectException(orgs_page_path)

        if invitation.status != OrgInvitation.Status.PENDING:
            gui.write(f"This invitation has been {invitation.get_status_display()}.")
            return

        gui.write(
            f"**{format_user_name(invitation.inviter)}** has invited you to join **{invitation.org.name}**."
        )

        if other_m := user.org_memberships.first():
            gui.caption(
                f"You are currently a member of [{other_m.org.name}]({orgs_page_path}). You will be removed from that team if you accept this invitation."
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
            raise gui.RedirectException(orgs_page_path)
        if reject_button:
            invitation.reject(user=user)


def orgs_page(user: AppUser):
    memberships = user.org_memberships.all()
    if not memberships:
        gui.write("*You're not part of an organization yet... Create one?*")

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

    with gui.div(
        className="d-xs-block d-sm-flex flex-row-reverse justify-content-between"
    ):
        with gui.div(className="d-flex justify-content-center align-items-center"):
            if membership.can_edit_org_metadata():
                org_edit_modal = gui.Modal("Edit Org", key="edit-org-modal")
                if org_edit_modal.is_open():
                    with org_edit_modal.container():
                        render_org_edit_view_by_membership(
                            membership, modal=org_edit_modal
                        )

                if gui.button(f"{icons.edit} Edit", type="secondary"):
                    org_edit_modal.open()

        with gui.div(className="d-flex align-items-center"):
            gui.image(
                org.logo or DEFAULT_ORG_LOGO,
                className="my-0 me-4 rounded",
                style={"width": "128px", "height": "128px", "object-fit": "contain"},
            )
            with gui.div(className="d-flex flex-column justify-content-center"):
                gui.write(f"# {org.name}")
                if org.domain_name:
                    gui.write(
                        f"Org Domain: `@{org.domain_name}`", className="text-muted"
                    )

    with gui.div(className="mt-4"):
        gui.write("# Billing")
        billing_section(org=org, current_member=membership)

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
                            org=org, inviter=current_user, modal=invite_modal
                        )

        render_members_list(org=org, current_member=membership)

    with gui.div(className="mt-4"):
        render_pending_invitations_list(org=org, current_member=membership)

    with gui.div(className="mt-4"):
        org_leave_modal = gui.Modal("Leave Org", key="leave-org-modal")
        if org_leave_modal.is_open():
            with org_leave_modal.container():
                render_org_leave_view_by_membership(membership, modal=org_leave_modal)

        with gui.div(className="text-end"):
            leave_org = gui.button(
                "Leave",
                className="btn btn-theme bg-danger border-danger text-white",
            )
        if leave_org:
            org_leave_modal.open()


def billing_section(*, org: Org, current_member: OrgMembership):
    render_payments_setup()

    if org.subscription and org.subscription.external_id:
        render_current_plan(org)

    with gui.div(className="my-5"):
        render_credit_balance(org)

    with gui.div(className="my-5"):
        selected_payment_provider = render_all_plans(org)

    with gui.div(className="my-5"):
        render_addon_section(org, selected_payment_provider)

    if org.subscription and org.subscription.external_id:
        # if org.subscription.payment_provider == PaymentProvider.STRIPE:
        #     with gui.div(className="my-5"):
        #         render_auto_recharge_section(user)
        with gui.div(className="my-5"):
            render_payment_information(org)

    with gui.div(className="my-5"):
        render_billing_history(org)


def render_payments_setup():
    from routers.account import payment_processing_route

    gui.html(
        templates.get_template("payment_setup.html").render(
            settings=settings,
            payment_processing_url=get_app_route_url(payment_processing_route),
        )
    )


def render_current_plan(org: Org):
    plan = PricingPlan.from_sub(org.subscription)
    provider = (
        PaymentProvider(org.subscription.payment_provider)
        if org.subscription.payment_provider
        else None
    )

    with gui.div(className=f"{rounded_border} border-dark"):
        # ROW 1: Plan title and next invoice date
        left, right = left_and_right()
        with left:
            gui.write(f"#### Gooey.AI {plan.title}")

            if provider:
                gui.write(
                    f"[{icons.edit} Manage Subscription](#payment-information)",
                    unsafe_allow_html=True,
                )
        with right, gui.div(className="d-flex align-items-center gap-1"):
            if provider and (
                next_invoice_ts := gui.run_in_thread(
                    org.subscription.get_next_invoice_timestamp, cache=True
                )
            ):
                gui.html("Next invoice on ")
                gui.pill(
                    "...",
                    text_bg="dark",
                    **render_local_date_attrs(
                        next_invoice_ts,
                        date_options={"day": "numeric", "month": "long"},
                    ),
                )

        if plan is PricingPlan.ENTERPRISE:
            # charge details are not relevant for Enterprise customers
            return

        # ROW 2: Plan pricing details
        left, right = left_and_right(className="mt-5")
        with left:
            gui.write(f"# {plan.pricing_title()}", className="no-margin")
            if plan.monthly_charge:
                provider_text = f" **via {provider.label}**" if provider else ""
                gui.caption("per month" + provider_text)

        with right, gui.div(className="text-end"):
            gui.write(f"# {plan.credits:,} credits", className="no-margin")
            if plan.monthly_charge:
                gui.write(
                    f"**${plan.monthly_charge:,}** monthly renewal for {plan.credits:,} credits"
                )


def render_credit_balance(org: Org):
    gui.write(f"## Credit Balance: {org.balance:,}")
    gui.caption(
        "Every time you submit a workflow or make an API call, we deduct credits from your account."
    )


def render_all_plans(org: Org) -> PaymentProvider | None:
    current_plan = (
        PricingPlan.from_sub(org.subscription)
        if org.subscription
        else PricingPlan.STARTER
    )
    all_plans = [plan for plan in PricingPlan if not plan.deprecated]

    gui.write("## All Plans")
    plans_div = gui.div(className="mb-1")

    if org.subscription and org.subscription.payment_provider:
        selected_payment_provider = None
    else:
        with gui.div():
            selected_payment_provider = PaymentProvider[
                payment_provider_radio() or PaymentProvider.STRIPE.name
            ]

    def _render_plan(plan: PricingPlan):
        if plan == current_plan:
            extra_class = "border-dark"
        else:
            extra_class = "bg-light"
        with gui.div(className="d-flex flex-column h-100"):
            with gui.div(
                className=f"{rounded_border} flex-grow-1 d-flex flex-column p-3 mb-2 {extra_class}"
            ):
                _render_plan_details(plan)
                # _render_plan_action_button(
                #     user, plan, current_plan, selected_payment_provider
                # )

    with plans_div:
        grid_layout(4, all_plans, _render_plan, separator=False)

    with gui.div(className="my-2 d-flex justify-content-center"):
        gui.caption(
            f"**[See all features & benefits]({settings.PRICING_DETAILS_URL})**"
        )

    return selected_payment_provider


def _render_plan_details(plan: PricingPlan):
    with gui.div(className="flex-grow-1"):
        with gui.div(className="mb-4"):
            with gui.tag("h4", className="mb-0"):
                gui.html(plan.title)
            gui.caption(
                plan.description,
                style={
                    "minHeight": "calc(var(--bs-body-line-height) * 2em)",
                    "display": "block",
                },
            )
        with gui.div(className="my-3 w-100"):
            with gui.tag("h4", className="my-0 d-inline me-2"):
                gui.html(plan.pricing_title())
            with gui.tag("span", className="text-muted my-0"):
                gui.html(plan.pricing_caption())
        gui.write(plan.long_description, unsafe_allow_html=True)


def render_payment_information(org: Org):
    assert org.subscription

    gui.write("## Payment Information", id="payment-information", className="d-block")
    col1, col2, col3 = gui.columns(3, responsive=False)
    with col1:
        gui.write("**Pay via**")
    with col2:
        provider = PaymentProvider(org.subscription.payment_provider)
        gui.write(provider.label)
    with col3:
        if gui.button(f"{icons.edit} Edit", type="link", key="manage-payment-provider"):
            raise gui.RedirectException(org.subscription.get_external_management_url())

    pm_summary = gui.run_in_thread(
        org.subscription.get_payment_method_summary, cache=True
    )
    if not pm_summary:
        return
    pm_summary = PaymentMethodSummary(*pm_summary)
    if pm_summary.card_brand and pm_summary.card_last4:
        col1, col2, col3 = gui.columns(3, responsive=False)
        with col1:
            gui.write("**Payment Method**")
        with col2:
            gui.write(
                f"{format_card_brand(pm_summary.card_brand)} ending in {pm_summary.card_last4}",
                unsafe_allow_html=True,
            )
        with col3:
            if gui.button(f"{icons.edit} Edit", type="link", key="edit-payment-method"):
                change_payment_method(org)

    if pm_summary.billing_email:
        col1, col2, _ = gui.columns(3, responsive=False)
        with col1:
            gui.write("**Billing Email**")
        with col2:
            gui.html(pm_summary.billing_email)


def change_payment_method(org: Org):
    from routers.account import payment_processing_route
    from routers.account import account_route

    match org.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            session = stripe.checkout.Session.create(
                mode="setup",
                currency="usd",
                customer=org.get_or_create_stripe_customer().id,
                setup_intent_data={
                    "metadata": {"subscription_id": org.subscription.external_id},
                },
                success_url=get_app_route_url(payment_processing_route),
                cancel_url=get_app_route_url(account_route),
            )
            raise gui.RedirectException(session.url, status_code=303)
        case _:
            gui.error("Not implemented for this payment provider")


def render_billing_history(org: Org, limit: int = 50):
    import pandas as pd

    txns = org.transactions.filter(amount__gt=0).order_by("-created_at")
    if not txns:
        return

    gui.write("## Billing History", className="d-block")
    gui.table(
        pd.DataFrame.from_records(
            [
                {
                    "Date": txn.created_at.strftime("%m/%d/%Y"),
                    "Description": txn.reason_note(),
                    "Amount": f"-${txn.charged_amount / 100:,.2f}",
                    "Credits": f"+{txn.amount:,}",
                    "Balance": f"{txn.end_balance:,}",
                }
                for txn in txns[:limit]
            ]
        ),
    )
    if txns.count() > limit:
        gui.caption(f"Showing only the most recent {limit} transactions.")


def render_addon_section(org: Org, selected_payment_provider: PaymentProvider):
    if org.subscription:
        gui.write("# Purchase More Credits")
    else:
        gui.write("# Purchase Credits")
    gui.caption(f"Buy more credits. $1 per {settings.ADDON_CREDITS_PER_DOLLAR} credits")

    if org.subscription and org.subscription.payment_provider:
        provider = PaymentProvider(org.subscription.payment_provider)
    else:
        provider = selected_payment_provider
    match provider:
        case PaymentProvider.STRIPE | None:
            render_stripe_addon_buttons(org)
        case PaymentProvider.PAYPAL:
            render_paypal_addon_buttons()


def render_paypal_addon_buttons():
    selected_amt = gui.horizontal_radio(
        "",
        settings.ADDON_AMOUNT_CHOICES,
        format_func=lambda amt: f"${amt:,}",
        checked_by_default=False,
    )
    if selected_amt:
        gui.js(
            f"setPaypalAddonQuantity({int(selected_amt) * settings.ADDON_CREDITS_PER_DOLLAR})"
        )
    gui.div(
        id="paypal-addon-buttons",
        className="mt-2",
        style={"width": "fit-content"},
    )
    gui.div(id="paypal-result-message")


def render_stripe_addon_buttons(org: Org):
    for dollar_amt in settings.ADDON_AMOUNT_CHOICES:
        render_stripe_addon_button(dollar_amt, org)


def render_stripe_addon_button(dollar_amt: int, org: Org):
    confirm_purchase_modal = gui.Modal(
        "Confirm Purchase", key=f"confirm-purchase-{dollar_amt}"
    )
    if gui.button(f"${dollar_amt:,}", type="primary"):
        if org.subscription and org.subscription.external_id:
            confirm_purchase_modal.open()
        else:
            stripe_addon_checkout_redirect(org, dollar_amt)

    if not confirm_purchase_modal.is_open():
        return
    with confirm_purchase_modal.container():
        gui.write(
            f"""
                Please confirm your purchase:  
                 **{dollar_amt * settings.ADDON_CREDITS_PER_DOLLAR:,} credits for ${dollar_amt}**.
                 """,
            className="py-4 d-block text-center",
        )
        with gui.div(className="d-flex w-100 justify-content-end"):
            if gui.session_state.get("--confirm-purchase"):
                success = gui.run_in_thread(
                    org.subscription.stripe_attempt_addon_purchase,
                    args=[dollar_amt],
                    placeholder="Processing payment...",
                )
                if success is None:
                    return
                gui.session_state.pop("--confirm-purchase")
                if success:
                    confirm_purchase_modal.close()
                else:
                    gui.error("Payment failed... Please try again.")
                return

            if gui.button("Cancel", className="border border-danger text-danger me-2"):
                confirm_purchase_modal.close()
            gui.button("Buy", type="primary", key="--confirm-purchase")


def stripe_addon_checkout_redirect(org: Org, dollar_amt: int):
    from routers.account import account_route
    from routers.account import payment_processing_route

    line_item = available_subscriptions["addon"]["stripe"].copy()
    line_item["quantity"] = dollar_amt * settings.ADDON_CREDITS_PER_DOLLAR
    checkout_session = stripe.checkout.Session.create(
        line_items=[line_item],
        mode="payment",
        success_url=get_app_route_url(payment_processing_route),
        cancel_url=get_app_route_url(account_route),
        customer=org.get_or_create_stripe_customer().id,
        invoice_creation={"enabled": True},
        allow_promotion_codes=True,
        saved_payment_method_options={
            "payment_method_save": "enabled",
        },
    )
    raise gui.RedirectException(checkout_session.url, status_code=303)


def render_org_creation_view(user: AppUser):
    gui.write(f"# {icons.company} Create an Org", unsafe_allow_html=True)
    org_fields = render_org_create_or_edit_form()

    if gui.button("Create"):
        try:
            Org.objects.create_org(
                created_by=user,
                **org_fields,
            )
        except ValidationError as e:
            gui.write(", ".join(e.messages), className="text-danger")
        else:
            gui.experimental_rerun()


def render_org_edit_view_by_membership(membership: OrgMembership, *, modal: gui.Modal):
    org = membership.org
    render_org_create_or_edit_form(org=org)

    if gui.button("Save", className="w-100", type="primary"):
        try:
            org.full_clean()
        except ValidationError as e:
            # newlines in markdown
            gui.write("  \n".join(e.messages), className="text-danger")
        else:
            org.save()
            modal.close()

    if membership.can_delete_org() or membership.can_transfer_ownership():
        gui.write("---")
        render_danger_zone_by_membership(membership)


def render_danger_zone_by_membership(membership: OrgMembership):
    gui.write("### Danger Zone", className="d-block my-2")

    if membership.can_delete_org():
        org_deletion_modal = gui.Modal("Delete Organization", key="delete-org-modal")
        if org_deletion_modal.is_open():
            with org_deletion_modal.container():
                render_org_deletion_view_by_membership(
                    membership, modal=org_deletion_modal
                )

        with gui.div(className="d-flex justify-content-between align-items-center"):
            gui.write("Delete Organization")
            if gui.button(
                f"{icons.delete} Delete",
                className="btn btn-theme py-2 bg-danger border-danger text-white",
            ):
                org_deletion_modal.open()


def render_org_deletion_view_by_membership(
    membership: OrgMembership, *, modal: gui.Modal
):
    gui.write(
        f"Are you sure you want to delete **{membership.org.name}**? This action is irreversible."
    )

    with gui.div(className="d-flex"):
        if gui.button(
            "Cancel", type="secondary", className="border-danger text-danger w-50"
        ):
            modal.close()

        if gui.button(
            "Delete", className="btn btn-theme bg-danger border-danger text-light w-50"
        ):
            membership.org.delete()
            modal.close()


def render_org_leave_view_by_membership(
    current_member: OrgMembership, *, modal: gui.Modal
):
    org = current_member.org

    gui.write("Are you sure you want to leave this organization?")

    new_owner = None
    if current_member.role == OrgRole.OWNER and org.memberships.count() == 1:
        gui.caption(
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

        gui.caption(
            "You are the only owner of this organization. Please choose another member to promote to owner."
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
                new_owner.role = OrgRole.OWNER
                new_owner.save()
            current_member.delete()
            modal.close()


def render_members_list(org: Org, current_member: OrgMembership):
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
            for m in org.memberships.all().order_by("created_at"):
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


def render_pending_invitations_list(org: Org, *, current_member: OrgMembership):
    pending_invitations = org.invitations.filter(status=OrgInvitation.Status.PENDING)
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
    email = gui.text_input("Email")
    if org.domain_name:
        gui.caption(
            f"Users with `@{org.domain_name}` email will be added automatically."
        )

    if gui.button(f"{icons.add_user} Invite", type="primary", unsafe_allow_html=True):
        try:
            org.invite_user(
                invitee_email=email,
                inviter=inviter,
                role=OrgRole.MEMBER,
                auto_accept=org.domain_name.lower() == email.split("@")[1].lower(),
            )
        except ValidationError as e:
            gui.write(", ".join(e.messages), className="text-danger")
        else:
            modal.close()


def render_org_create_or_edit_form(org: Org | None = None) -> AttrDict | Org:
    org_proxy = org or AttrDict()

    org_proxy.name = gui.text_input("Team Name", value=org and org.name or "")
    org_proxy.logo = gui.file_uploader(
        "Logo", accept=["image/*"], value=org and org.logo or ""
    )
    org_proxy.domain_name = gui.text_input(
        "Domain Name (Optional)",
        placeholder="e.g. gooey.ai",
        value=org and org.domain_name or "",
    )
    if org_proxy.domain_name:
        gui.caption(
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


def left_and_right(*, className: str = "", **props):
    className += " d-flex flex-row justify-content-between align-items-center"
    with gui.div(className=className, **props):
        return gui.div(), gui.div()
