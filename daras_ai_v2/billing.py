import typing
from datetime import datetime
from functools import partial

import gooey_gui as gui
import sentry_sdk
import stripe
from django.core.exceptions import ValidationError
from django.utils.translation import ngettext
from loguru import logger

from app_users.models import AppUserTransaction, PaymentProvider
from daras_ai_v2 import icons, settings, paypal
from daras_ai_v2.fastapi_tricks import get_app_route_url, get_route_path
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.settings import templates
from daras_ai_v2.user_date_widgets import render_local_date_attrs
from payments.models import PaymentMethodSummary
from payments.plans import PricingPlan
from payments.webhooks import StripeWebhookHandler, set_workspace_subscription
from scripts.migrate_existing_subscriptions import available_subscriptions
from widgets.author import render_author_from_workspace
from workspaces.widgets import open_create_workspace_popup_js, set_current_workspace

if typing.TYPE_CHECKING:
    from app_users.models import AppUser
    from workspaces.models import Workspace, WorkspaceSeatType


rounded_border = "w-100 border shadow-sm rounded py-4 px-3"
SeatSelection = tuple["WorkspaceSeatType", int]


def _is_plan_with_db_seat_options(plan: PricingPlan) -> bool:
    return plan in (PricingPlan.TEAM, PricingPlan.STANDARD)


def _get_workspace_seat_options(
    workspace: "Workspace", plan: PricingPlan
) -> list["WorkspaceSeatType"]:
    from workspaces.models import WorkspaceSeatType

    if not _is_plan_with_db_seat_options(plan):
        return []
    return list(
        WorkspaceSeatType.objects.filter(monthly_charge__gt=0).order_by(
            "monthly_charge", "monthly_credit_limit", "name", "id"
        )
    )


def _seat_selection_monthly_charge(
    selection: SeatSelection | None, fallback_plan: PricingPlan
) -> int:
    if not selection:
        return fallback_plan.get_active_monthly_charge()
    seat_type, seats = selection
    return seat_type.monthly_charge * seats


def _seat_selection_credits(
    selection: SeatSelection | None, fallback_plan: PricingPlan
) -> int:
    if not selection:
        return fallback_plan.get_active_credits()
    seat_type, seats = selection
    return (seat_type.monthly_credit_limit or 0) * seats


def _apply_default_team_seat_type_to_members(
    workspace: "Workspace", selection: SeatSelection | None
) -> None:
    if not selection:
        return
    seat_type, _ = selection
    workspace.memberships.filter(
        deleted__isnull=True,
    ).exclude(
        seat_type__monthly_charge=0,
    ).update(seat_type=seat_type)


def _get_scheduled_team_downgrade_info(
    subscription_model,
) -> dict[str, typing.Any] | None:
    if (
        not subscription_model
        or subscription_model.payment_provider != PaymentProvider.STRIPE
        or not subscription_model.external_id
    ):
        return None

    stripe_sub = stripe.Subscription.retrieve(
        subscription_model.external_id, expand=["schedule"]
    )
    schedule = stripe_sub.get("schedule")
    if not schedule:
        return None
    if isinstance(schedule, str):
        schedule = stripe.SubscriptionSchedule.retrieve(
            schedule, expand=["phases.items.price"]
        )

    current_period_end = stripe_sub.get("current_period_end")
    if not current_period_end:
        return None

    for phase in schedule.get("phases", []):
        start_date = phase.get("start_date")
        if not start_date or start_date < current_period_end:
            continue

        metadata = phase.get("metadata") or {}
        plan_key = metadata.get(settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD)
        if not plan_key:
            continue
        try:
            plan = PricingPlan.get_by_key(plan_key)
        except KeyError:
            continue

        seats = metadata.get("seats") or str(
            getattr(subscription_model, "seats", 1) or 1
        )
        seat_type_name = metadata.get("seat_type_name") or "Selected seat type"
        seat_monthly_credit_limit = metadata.get("seat_monthly_credit_limit")
        seat_monthly_charge = metadata.get("seat_monthly_charge")
        try:
            seat_monthly_credit_limit_int = (
                int(seat_monthly_credit_limit)
                if seat_monthly_credit_limit is not None
                else None
            )
        except (TypeError, ValueError):
            seat_monthly_credit_limit_int = None
        try:
            seat_monthly_charge_int = (
                int(seat_monthly_charge) if seat_monthly_charge is not None else None
            )
        except (TypeError, ValueError):
            seat_monthly_charge_int = None

        total_monthly_charge = None
        phase_items = phase.get("items") or []
        if phase_items:
            item = phase_items[0]
            price = item.get("price")
            quantity = item.get("quantity")
            try:
                quantity_int = int(quantity or 0)
            except (TypeError, ValueError):
                quantity_int = 0
            if quantity_int:
                if isinstance(price, dict):
                    price_obj = price
                elif isinstance(price, str):
                    price_obj = stripe.Price.retrieve(price)
                else:
                    price_obj = None

                if price_obj:
                    unit_amount = price_obj.get("unit_amount")
                    if (
                        unit_amount is None
                        and price_obj.get("unit_amount_decimal") is not None
                    ):
                        unit_amount = int(float(price_obj["unit_amount_decimal"]))
                    if unit_amount is not None:
                        total_monthly_charge = int(
                            round((unit_amount * quantity_int) / 100)
                        )

        if total_monthly_charge is None and seat_monthly_charge_int is not None:
            total_monthly_charge = seat_monthly_charge_int * int(seats)

        return dict(
            plan_title=plan.title,
            plan_db_value=plan.db_value,
            seat_type_name=seat_type_name,
            seat_monthly_credit_limit=seat_monthly_credit_limit_int,
            seat_monthly_charge=seat_monthly_charge_int,
            total_monthly_charge=total_monthly_charge,
            seats=int(seats),
            effective_date=datetime.fromtimestamp(start_date).strftime("%d %b %Y"),
        )

    return None


def _schedule_team_plan_change_next_cycle(
    *,
    subscription: stripe.Subscription,
    new_plan: PricingPlan,
    new_selection: SeatSelection,
):
    new_line_item = new_plan.get_stripe_line_item(
        credits=_seat_selection_credits(new_selection, new_plan),
        monthly_charge=_seat_selection_monthly_charge(new_selection, new_plan),
        product_name=f"{new_plan.title} - {new_selection[0].name}",
    )
    new_metadata = dict(subscription.metadata or {})
    new_metadata[settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD] = new_plan.key
    new_metadata["seats"] = str(new_selection[1])
    new_metadata["seat_type_name"] = new_selection[0].name
    new_metadata["seat_monthly_credit_limit"] = str(
        new_selection[0].monthly_credit_limit or 0
    )
    new_metadata["seat_monthly_charge"] = str(new_selection[0].monthly_charge)

    schedule_id = subscription.get("schedule")
    if schedule_id:
        # Existing schedules may contain ended phases, which Stripe does not allow
        # us to update directly for this use-case. Releasing avoids phase-index issues.
        stripe.SubscriptionSchedule.release(schedule_id)
    schedule = stripe.SubscriptionSchedule.create(
        from_subscription=subscription.id, expand=["phases.items.price"]
    )
    current_phase = (schedule.get("phases") or [None])[0]
    assert current_phase is not None, "Subscription schedule missing current phase"
    current_phase_start = current_phase.get("start_date")
    assert current_phase_start, "Current schedule phase start_date is missing"
    current_phase_items = current_phase.get("items") or []
    assert current_phase_items, "Current schedule phase items are missing"
    current_phase_item = current_phase_items[0]
    current_phase_price = current_phase_item.get("price")
    assert current_phase_price and current_phase_price.get("id"), (
        "Current schedule phase price is missing"
    )

    stripe.SubscriptionSchedule.modify(
        schedule.id,
        end_behavior="release",
        proration_behavior="none",
        phases=[
            dict(
                start_date=current_phase_start,
                end_date=subscription.current_period_end,
                items=[
                    dict(
                        price=current_phase_price["id"],
                        quantity=current_phase_item.get("quantity") or 1,
                    )
                ],
                metadata=dict(subscription.metadata or {}),
                proration_behavior="none",
            ),
            dict(
                start_date=subscription.current_period_end,
                items=[
                    dict(
                        price_data=new_line_item["price_data"],
                        quantity=new_line_item["quantity"],
                    )
                ],
                metadata=new_metadata,
                proration_behavior="none",
            ),
        ],
    )


def billing_page(workspace: "Workspace", user: "AppUser", session: dict):
    render_payments_setup()

    if len(user.cached_workspaces) > 1:
        # when user has multiple workspaces, remind them of the one they are currently on
        with gui.div(className="mb-3"):
            render_author_from_workspace(workspace, show_as_link=False)

    if (
        workspace.subscription
        and workspace.subscription.is_paid()
        and workspace.subscription.plan != PricingPlan.ENTERPRISE.db_value
    ):
        with gui.div(className="mb-5"):
            render_current_plan(workspace)

    with gui.div(className="mb-5"):
        render_credit_balance(workspace)

    with gui.div(className="mb-5"):
        selected_payment_provider = render_all_plans(
            workspace, user=user, session=session
        )

    with gui.div(className="mb-5"):
        render_addon_section(workspace, selected_payment_provider)

    if workspace.subscription:
        if workspace.subscription.payment_provider == PaymentProvider.STRIPE:
            with gui.div(className="mb-5"):
                render_auto_recharge_section(workspace)

        with gui.div(className="mb-5"):
            render_payment_information(workspace)

    with gui.div(className="mb-5"):
        render_billing_history(workspace)


def render_payments_setup():
    from routers.account import payment_processing_route

    gui.html(
        templates.get_template("payment_setup.html").render(
            settings=settings,
            payment_processing_url=get_app_route_url(payment_processing_route),
        )
    )


def render_current_plan(workspace: "Workspace"):
    plan = PricingPlan.from_sub(workspace.subscription)
    selected_seat_type = workspace.subscription.get_seat_type()
    seats = max(1, workspace.subscription.seats or 1)
    if selected_seat_type:
        monthly_charge = selected_seat_type.monthly_charge * seats
        credits = (selected_seat_type.monthly_credit_limit or 0) * seats
    else:
        monthly_charge = plan.get_active_monthly_charge()
        credits = plan.get_active_credits()

    if workspace.subscription.payment_provider:
        provider = PaymentProvider(workspace.subscription.payment_provider)
    else:
        provider = None

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
                    workspace.subscription.get_next_invoice_timestamp, cache=True
                )
            ):
                gui.html("Next invoice on ")
                with gui.tag("span", className="badge rounded-pill text-bg-dark"):
                    gui.html(
                        "...",
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
            gui.write(f"# ${monthly_charge:,}/month", className="no-margin")
            if monthly_charge:
                if provider:
                    provider_text = f" **via {provider.label}**"
                else:
                    provider_text = ""
                gui.caption("per month" + provider_text)

        with right, gui.div(className="text-end"):
            if seats > 1:
                gui.write(
                    f"# {seats} seats & {credits:,} credits", className="no-margin"
                )
            else:
                gui.write(f"# {credits:,} credits", className="no-margin")

            if monthly_charge:
                text = f"**${monthly_charge:,}** monthly renewal for "
                if selected_seat_type and seats > 1:
                    text += (
                        f"{seats} seats with "
                        f"{selected_seat_type.monthly_credit_limit or 0:,} credits each"
                    )
                else:
                    text += f"{credits:,} credits"
                gui.caption(text)

        scheduled_downgrade = gui.run_in_thread(
            _get_scheduled_team_downgrade_info,
            args=[workspace.subscription],
            cache=True,
        )
        if scheduled_downgrade:
            target_seats = scheduled_downgrade["seats"]
            target_credits = scheduled_downgrade.get("seat_monthly_credit_limit")
            total_monthly = scheduled_downgrade.get("total_monthly_charge")
            if target_credits is not None and total_monthly is not None:
                change_text = (
                    f"{target_credits:,} credits / month × {target_seats} seats "
                    f"(${total_monthly:,} / month)"
                )
            elif target_credits is not None:
                change_text = (
                    f"{target_credits:,} credits / month × {target_seats} seats"
                )
            elif total_monthly is not None:
                change_text = (
                    f"{scheduled_downgrade['seat_type_name']} × {target_seats} seats "
                    f"(${total_monthly:,} / month)"
                )
            else:
                change_text = (
                    f"{scheduled_downgrade['plan_title']} "
                    f"({scheduled_downgrade['seat_type_name']}) "
                    f"× {target_seats} seats"
                )

            gui.caption(
                f"Scheduled change to: **{change_text}**, "
                f"effective **{scheduled_downgrade['effective_date']}**."
            )


def render_credit_balance(workspace: "Workspace"):
    gui.write(f"## Credit Balance: {workspace.balance:,}")
    gui.caption(
        "Every time you submit a workflow or make an API call, we deduct credits from your account."
    )


def render_all_plans(
    workspace: "Workspace", user: "AppUser", session: dict
) -> PaymentProvider:
    current_plan = PricingPlan.from_sub(workspace.subscription)

    all_plans = [plan for plan in PricingPlan if not plan.deprecated]
    if not workspace.is_personal and current_plan != PricingPlan.STANDARD:
        all_plans.remove(PricingPlan.STANDARD)
    grid_plans = [plan for plan in all_plans if not plan.full_width]
    full_width_plans = [plan for plan in all_plans if plan.full_width]

    gui.write("## Plans")
    plans_div = gui.div(className="mb-1")

    if workspace.subscription and workspace.subscription.payment_provider:
        selected_payment_provider = workspace.subscription.payment_provider
    else:
        selected_payment_provider = PaymentProvider.STRIPE

    with plans_div:
        with gui.div(className="mb-1"):
            partial_fn = partial(
                _render_plan_compact,
                workspace=workspace,
                user=user,
                session=session,
                selected_payment_provider=selected_payment_provider,
            )
            grid_layout(len(grid_plans), grid_plans, partial_fn, separator=False)
        for plan in full_width_plans:
            with gui.div(className="mb-1"):
                _render_plan_full_width(
                    plan, workspace, user, session, selected_payment_provider
                )

    with gui.div(className="my-2 d-flex justify-content-center"):
        gui.caption(
            f"**[See all features & benefits]({settings.PRICING_DETAILS_URL})**"
        )

    return selected_payment_provider


def _render_plan_full_width(
    plan: PricingPlan,
    workspace: "Workspace",
    user: "AppUser",
    session: dict,
    selected_payment_provider: PaymentProvider,
):
    current_plan = PricingPlan.from_sub(workspace.subscription)

    if plan == current_plan:
        extra_class = "border-dark"
    else:
        extra_class = "bg-light"
    with (
        gui.div(className="d-flex flex-column h-100"),
        gui.div(className=f"{rounded_border} mb-2 {extra_class}"),
    ):
        _render_plan_heading(plan)
        with gui.div(className="row-lg d-flex flex-column flex-lg-row flex-grow-1"):
            with gui.div(
                className="col-lg-4 d-flex flex-column justify-content-between"
            ):
                with gui.div(className="mb-3"):
                    selected_tier = _render_plan_pricing(
                        plan, selected_payment_provider, workspace
                    )
                with gui.div(className="d-none d-lg-flex flex-column"):
                    _render_plan_action_button(
                        workspace=workspace,
                        plan=plan,
                        payment_provider=selected_payment_provider,
                        user=user,
                        session=session,
                        selected_tier=selected_tier,
                    )
            with gui.div(className="col-lg-8"):
                _render_plan_details(plan)
        with gui.div(className="d-flex d-lg-none flex-column my-3"):
            _render_plan_action_button(
                workspace=workspace,
                plan=plan,
                payment_provider=selected_payment_provider,
                user=user,
                session=session,
                selected_tier=selected_tier,
            )


def _render_plan_compact(
    plan: PricingPlan,
    workspace: "Workspace",
    user: "AppUser",
    session: dict,
    selected_payment_provider: PaymentProvider,
):
    current_plan = PricingPlan.from_sub(workspace.subscription)

    if plan == current_plan:
        extra_class = "border-dark"
    else:
        extra_class = "bg-light"
    with (
        gui.div(className="d-flex flex-column h-100"),
        gui.div(
            className=f"{rounded_border} flex-grow-1 d-flex flex-column mb-2 {extra_class}"
        ),
    ):
        _render_plan_heading(plan)
        selected_tier = _render_plan_pricing(plan, selected_payment_provider, workspace)
        with gui.div(
            className="flex-grow-1 d-flex flex-column justify-content-between"
        ):
            _render_plan_details(plan)
        with gui.div(className="mt-3 d-flex flex-column"):
            _render_plan_action_button(
                workspace=workspace,
                plan=plan,
                payment_provider=selected_payment_provider,
                user=user,
                session=session,
                selected_tier=selected_tier,
            )


def _render_plan_details(plan: PricingPlan):
    """Render plan details and return selected tier key if plan has tiers"""
    with gui.div(className="mt-3"):
        gui.write(plan.long_description, unsafe_allow_html=True)
    with gui.div(className="mt-3"):
        gui.write(plan.footer, unsafe_allow_html=True)


def _render_plan_heading(plan: PricingPlan):
    with gui.tag("h2", className="mb-1"):
        gui.html(plan.title)
    gui.caption(
        plan.description,
        unsafe_allow_html=True,
        style={
            "minHeight": "calc(var(--bs-body-line-height) * 2em)",
            "display": "block",
        },
    )


def _render_plan_pricing(
    plan: PricingPlan, payment_provider: PaymentProvider | None, workspace: "Workspace"
) -> SeatSelection | None:
    pricing_div = gui.div()

    if payment_provider != PaymentProvider.STRIPE:
        selected_tier = None
    elif not _is_plan_with_db_seat_options(plan):
        selected_tier = None
    else:
        current_seat_type = (
            workspace.subscription and workspace.subscription.get_seat_type()
        )
        seat_options = _get_workspace_seat_options(workspace, plan)
        if not seat_options:
            selected_tier = None
            with pricing_div:
                with gui.tag("h3", className="my-0 d-inline me-2"):
                    gui.html(plan.get_pricing_title())
                if caption := plan.get_pricing_caption():
                    with gui.tag("p", className="text-muted my-0"):
                        gui.html(caption)
            return selected_tier

        colspec = [3, 1] if plan == PricingPlan.TEAM else [12, 0]
        col1, col2 = gui.columns(colspec, responsive=True)
        with col1:
            seat_type_id: int = gui.selectbox(
                label="Monthly credits per member",
                options=[seat.id for seat in seat_options],
                format_func=lambda seat_id: next(
                    (
                        f"{seat.monthly_credit_limit or 0:,} credits/month"
                        f" for ${seat.monthly_charge}/seat"
                    )
                    for seat in seat_options
                    if seat.id == seat_id
                ),
                key=f"tier-select-{plan.key}",
                value=(current_seat_type and current_seat_type.id),
                className="mb-0 container-margin-reset",
            )
            selected_workspace_seat_type = next(
                seat for seat in seat_options if seat.id == seat_type_id
            )

        if plan == PricingPlan.TEAM:
            with col2:
                seats: int = gui.selectbox(
                    label="Seats",
                    options=[1, 2, 3, 4, 5, 10, 15, 20, 25, 50],
                    key=f"seats-select-{plan.key}-{workspace.id}",
                    value=(
                        workspace.subscription
                        and max(1, workspace.subscription.seats or 1)
                        or workspace.used_seats
                    ),
                    className="mb-0 container-margin-reset",
                )
        else:
            seats = 1

        selected_tier = (selected_workspace_seat_type, seats)

    with pricing_div:
        with gui.tag("h3", className="my-0 d-inline me-2"):
            gui.html(f"${_seat_selection_monthly_charge(selected_tier, plan):,}/month")
        if caption := plan.get_pricing_caption():
            with gui.tag("p", className="text-muted my-0"):
                gui.html(caption)

    return selected_tier


def _render_plan_action_button(
    *,
    workspace: "Workspace",
    user: "AppUser",
    plan: PricingPlan,
    payment_provider: PaymentProvider | None,
    session: dict,
    selected_tier: SeatSelection | None = None,
):
    current_plan = PricingPlan.from_sub(workspace.subscription)
    current_seat_type = (
        workspace.subscription and workspace.subscription.get_seat_type()
    )
    current_seats = (
        workspace.subscription and max(1, workspace.subscription.seats or 1) or 1
    )

    if plan == current_plan and (
        not _is_plan_with_db_seat_options(plan)
        or (
            workspace.subscription
            and selected_tier
            and current_seat_type == selected_tier[0]
            and current_seats == selected_tier[1]
        )
    ):
        gui.button("Your Plan", className="w-100", disabled=True, type="tertiary")

    elif current_plan == PricingPlan.ENTERPRISE:
        gui.button(
            "N/A",
            className="d-none d-lg-inline w-100 opacity-0",
            disabled=True,
            type="tertiary",
        )

    elif plan.contact_us_link:
        with gui.link(to=plan.contact_us_link, className="btn btn-theme btn-primary"):
            gui.html("Let's Talk")

    elif (
        plan == PricingPlan.TEAM
        and workspace.is_personal
        and any(
            w.subscription and w.subscription.plan == plan.db_value
            for w in user.cached_workspaces
        )
    ):
        _render_switch_workspace_button(workspace=workspace, user=user, session=session)

    elif workspace.subscription and workspace.subscription.is_paid():
        render_change_subscription_button(
            workspace=workspace,
            plan=plan,
            selected_tier=selected_tier,
        )

    else:
        assert payment_provider is not None
        _render_create_subscription_button(
            workspace=workspace,
            plan=plan,
            payment_provider=payment_provider,
            selected_tier=selected_tier,
        )


def _render_switch_workspace_button(
    workspace: "Workspace", user: "AppUser", session: dict
):
    from routers.account import members_route

    workspace_select_dialog = gui.use_confirm_dialog(
        "workspace-select-dialog", close_on_confirm=False
    )
    options: dict[int, Workspace] = {
        w.id: w for w in user.cached_workspaces if w != workspace
    }
    if gui.button("Switch to a Workspace", type="secondary"):
        if len(options) == 1:
            set_current_workspace(session=session, workspace_id=options.popitem()[0])
            raise gui.RedirectException(get_route_path(members_route))
        else:
            workspace_select_dialog.set_open(True)

    if workspace_select_dialog.is_open:
        with gui.confirm_dialog(
            ref=workspace_select_dialog,
            modal_title="#### Switch Workspace",
            confirm_label="Switch",
        ):
            selected_workspace_id = gui.selectbox(
                "###### Select a Workspace",
                options=options,
                format_func=lambda w: options[w].display_html(current_user=user),
            )
        if workspace_select_dialog.pressed_confirm:
            set_current_workspace(session=session, workspace_id=selected_workspace_id)
            raise gui.RedirectException(get_route_path(members_route))


def render_change_subscription_button(
    *,
    workspace: "Workspace",
    plan: PricingPlan,
    selected_tier: SeatSelection | None = None,
):
    # subscription exists, show upgrade/downgrade button
    from routers.account import members_route

    current_plan = PricingPlan.from_sub(workspace.subscription)
    current_seat_type = (
        workspace.subscription and workspace.subscription.get_seat_type()
    )
    current_seat_selection = (
        (
            current_seat_type,
            workspace.subscription and max(1, workspace.subscription.seats or 1) or 1,
        )
        if current_seat_type
        else None
    )
    current_monthly_charge = _seat_selection_monthly_charge(
        current_seat_selection, current_plan
    )

    selected_monthly_charge = _seat_selection_monthly_charge(selected_tier, plan)
    selected_seats = selected_tier and selected_tier[1] or 1

    if not workspace.is_personal and workspace.used_seats > selected_seats:
        if selected_monthly_charge > current_monthly_charge:
            label, btn_type = "Upgrade", "primary"
        else:
            label, btn_type = "Downgrade", "secondary"

        ref = gui.use_alert_dialog(key=f"--modal-{plan.key}")
        if gui.button(label, type=btn_type):
            ref.set_open(True)

        if ref.is_open:
            with gui.alert_dialog(
                ref, modal_title=f"#### {icons.alert} Alert", unsafe_allow_html=True
            ):
                gui.write(f"""
You are currently using **{workspace.used_seats} seats** in this workspace.

Please select a plan with at least {workspace.used_seats} seats or remove some members in order to switch to this plan.

[View Members]({get_route_path(members_route)})
                """)
        return

    if plan > current_plan or (
        plan == current_plan
        and _is_plan_with_db_seat_options(plan)
        and selected_monthly_charge > current_monthly_charge
    ):
        _render_upgrade_subscription_button(
            workspace=workspace, plan=plan, selected_tier=selected_tier
        )
        return

    ref = gui.use_confirm_dialog(key=f"--modal-{plan.key}")
    next_invoice_ts = gui.run_in_thread(
        workspace.subscription.get_next_invoice_timestamp, cache=True
    )
    if next_invoice_ts:
        effective_date = datetime.fromtimestamp(next_invoice_ts).strftime("%d %b %Y")
        effective_text = (
            f"This will take effect from the next billing cycle "
            f"({effective_date} onwards)."
        )
    else:
        effective_text = "This will take effect from the next billing cycle."

    gui.button_with_confirm_dialog(
        ref=ref,
        trigger_label="Downgrade",
        modal_title="#### Downgrade Plan",
        modal_content=f"""
Are you sure you want to downgrade from: **{current_plan.title} @ {fmt_price(current_monthly_charge)}** to **{plan.title} @ {fmt_price(selected_monthly_charge)}**?

{effective_text}
    """,
        confirm_label="Downgrade",
        confirm_className="border-danger bg-danger text-white",
    )
    if ref.pressed_confirm:
        change_subscription(workspace, new_plan=plan, new_tier=selected_tier)


def _render_upgrade_subscription_button(
    *,
    workspace: "Workspace",
    plan: PricingPlan,
    selected_tier: SeatSelection | None = None,
):
    current_plan = PricingPlan.from_sub(workspace.subscription)
    current_tier = workspace.subscription.get_seat_type()

    upgrade_dialog = gui.use_confirm_dialog(
        key=f"upgrade-workspace-{workspace.id}-plan-{plan.key}-{current_tier}"
    )

    # Standard plan is only for personal workspaces, skip workspace creation popup
    if workspace.is_personal and plan != PricingPlan.STANDARD:
        if gui.button(
            "Create Team",
            type="primary",
            onClick=open_create_workspace_popup_js(selected_plan=plan),
        ):
            gui.session_state["pressed_create_workspace"] = True
        return
    elif gui.session_state.pop("pressed_create_workspace", None):
        upgrade_dialog.set_open(True)

    # For TEAM plan on team workspaces, show detailed order summary
    if plan == PricingPlan.TEAM:
        assert selected_tier is not None

        modal_content = get_order_summary_content(plan, selected_tier)
        confirm_label = "Upgrade"
        modal_title = "#### Order Summary"
    else:
        current_selection = (
            (
                current_tier,
                max(1, workspace.subscription.seats or 1),
            )
            if current_tier
            else None
        )
        current_monthly_charge = _seat_selection_monthly_charge(
            current_selection, current_plan
        )
        new_monthly_charge = _seat_selection_monthly_charge(selected_tier, plan)
        credits = _seat_selection_credits(selected_tier, plan)

        modal_content = f"""
Are you sure you want to upgrade from **{current_plan.title} @ {fmt_price(current_monthly_charge)}** to **{plan.title} @ {fmt_price(new_monthly_charge)}**?

Your payment method will be charged ${new_monthly_charge:,} today and again every month until you cancel.

**{credits:,} Credits** will be added to your account today and with subsequent payments, your account balance will be topped-up with {credits:,} Credits.
        """
        confirm_label = "Upgrade"
        modal_title = "#### Upgrade Plan"

    gui.button_with_confirm_dialog(
        ref=upgrade_dialog,
        trigger_label="Upgrade",
        trigger_type="primary",
        modal_title=modal_title,
        modal_content=modal_content,
        confirm_label=confirm_label,
    )

    if upgrade_dialog.pressed_confirm:
        try:
            change_subscription(
                workspace,
                new_plan=plan,
                new_tier=selected_tier,
                # when upgrading, charge the full new amount today: https://docs.stripe.com/billing/subscriptions/billing-cycle#reset-the-billing-cycle-to-the-current-time
                billing_cycle_anchor="now",
                payment_behavior="error_if_incomplete",
            )
        except (stripe.CardError, stripe.InvalidRequestError) as e:
            if isinstance(e, stripe.InvalidRequestError):
                sentry_sdk.capture_exception(e)
                logger.warning(e)

            # only handle error if it's related to mandates
            # cancel current subscription & redirect user to new subscription page
            workspace.subscription.cancel()
            stripe_subscription_create(workspace, plan, tier=selected_tier)


def _render_create_subscription_button(
    *,
    workspace: "Workspace",
    plan: PricingPlan,
    payment_provider: PaymentProvider,
    selected_tier: SeatSelection | None = None,
):
    # Standard plan is only for personal workspaces, skip workspace creation popup
    if workspace.is_personal and plan != PricingPlan.STANDARD:
        if gui.button(
            "Create Team",
            type="primary",
            onClick=open_create_workspace_popup_js(selected_plan=plan),
        ):
            gui.session_state["pressed_create_workspace"] = True
    elif plan == PricingPlan.TEAM and not workspace.is_personal:
        assert selected_tier is not None

        # For TEAM plan on team workspaces, show order summary modal first
        _render_team_plan_order_summary_button(
            workspace=workspace,
            plan=plan,
            payment_provider=payment_provider,
            selected_tier=selected_tier,
        )
    else:
        match payment_provider:
            case PaymentProvider.STRIPE:
                pressed = gui.session_state.pop("pressed_create_workspace", False)
                render_stripe_subscription_button(
                    label="Upgrade",
                    workspace=workspace,
                    plan=plan,
                    pressed=pressed,
                    tier=selected_tier,
                )
            case PaymentProvider.PAYPAL:
                # PayPal doesn't support tiers, use default
                render_paypal_subscription_button(plan=plan)


def get_order_summary_content(plan: PricingPlan, selected_tier: SeatSelection):
    from routers.account import members_route

    seat_type, selected_seats = selected_tier
    per_seat_charge = seat_type.monthly_charge
    total_charge = per_seat_charge * selected_seats
    extra_seats = selected_seats - 1

    # Build extra seats line only if there are extra seats
    if extra_seats > 0:
        extra_seats_title = (
            f"{extra_seats} extra paid {ngettext('seat', 'seats', extra_seats)} "
        )
        extra_seats_line = f"""
**{extra_seats_title:·<40} ${extra_seats * per_seat_charge}**
{extra_seats} x ${per_seat_charge}/month
[View members]({get_route_path(members_route)})
"""
    else:
        extra_seats_line = f"[View members]({get_route_path(members_route)})\n"

    plan_tier_title = f"{plan.title} {per_seat_charge} Plan "

    return f"""
**Monthly credits per member**
{seat_type.monthly_credit_limit or 0:,} / month

**{plan_tier_title:·<40} ${per_seat_charge}**
Base of ${per_seat_charge}/month

{extra_seats_line}

**{"Total ":·<48} ${total_charge}**

---

Your payment method will be charged **${total_charge:,}** today and again every month until you cancel.
    """


def _render_team_plan_order_summary_button(
    *,
    workspace: "Workspace",
    plan: PricingPlan,
    payment_provider: PaymentProvider,
    selected_tier: SeatSelection,
):
    """Render order summary modal for team plan upgrades"""
    order_summary_dialog = gui.use_confirm_dialog(
        key=f"team-order-summary-{plan.key}", close_on_confirm=False
    )

    if gui.button("Upgrade", type="primary"):
        order_summary_dialog.set_open(True)

    if order_summary_dialog.is_open:
        gui.confirm_dialog(
            ref=order_summary_dialog,
            modal_title="#### Order Summary",
            modal_content=get_order_summary_content(plan, selected_tier),
            confirm_label="Checkout",
        )

    if order_summary_dialog.pressed_confirm:
        # User confirmed, now proceed with the actual subscription creation
        match payment_provider:
            case PaymentProvider.STRIPE:
                render_stripe_subscription_button(
                    label="Checkout",
                    workspace=workspace,
                    plan=plan,
                    pressed=True,  # Skip the subscription button and go directly to payment
                    tier=selected_tier,
                )
            case PaymentProvider.PAYPAL:
                # PayPal doesn't support tiers or seats
                render_paypal_subscription_button(plan=plan)


def fmt_price(monthly_charge: int) -> str:
    if monthly_charge:
        return f"${monthly_charge:,}/month"
    else:
        return "Free"


def change_subscription(
    workspace: "Workspace",
    new_plan: PricingPlan,
    new_tier: SeatSelection | None = None,
    **kwargs,
):
    from routers.account import account_route
    from routers.account import payment_processing_route

    current_plan = PricingPlan.from_sub(workspace.subscription)

    # Check if plan and tier are both unchanged
    current_seat_type = (
        workspace.subscription and workspace.subscription.get_seat_type()
    )
    current_seats = (
        workspace.subscription and max(1, workspace.subscription.seats or 1) or 1
    )
    if (
        new_plan == current_plan
        and workspace.subscription
        and (
            (not new_tier and not current_seat_type)
            or (
                new_tier
                and current_seat_type == new_tier[0]
                and current_seats == new_tier[1]
            )
        )
    ):
        raise gui.RedirectException(get_app_route_url(account_route), status_code=303)

    if new_plan == PricingPlan.STARTER:
        workspace.subscription.cancel()
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )

    match workspace.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            if not new_plan.supports_stripe():
                gui.error(f"Stripe subscription not available for {new_plan}")

            subscription = stripe.Subscription.retrieve(
                workspace.subscription.external_id,
                expand=["items.data.price"],
            )

            is_team_to_team_change = (
                current_plan == PricingPlan.TEAM
                and new_plan == PricingPlan.TEAM
                and bool(new_tier)
            )
            if is_team_to_team_change:
                current_monthly_charge = round(
                    (workspace.subscription.charged_amount or 0) / 100
                )
                new_monthly_charge = _seat_selection_monthly_charge(new_tier, new_plan)
                if new_monthly_charge < current_monthly_charge:
                    _schedule_team_plan_change_next_cycle(
                        subscription=subscription,
                        new_plan=new_plan,
                        new_selection=new_tier,
                    )
                    raise gui.RedirectException(
                        get_app_route_url(payment_processing_route), status_code=303
                    )
                # Team seat upgrades are prorated immediately, but keep billing cycle.
                kwargs.pop("billing_cycle_anchor", None)
                kwargs["proration_behavior"] = "always_invoice"

            # Build metadata with tier info
            metadata = {
                settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: new_plan.key,
                "seats": str(new_tier[1]) if new_tier else "1",
            }
            kwargs.setdefault("proration_behavior", "none")

            stripe.Subscription.modify(
                subscription.id,
                items=[
                    {"id": subscription["items"].data[0], "deleted": True},
                    new_plan.get_stripe_line_item(
                        credits=_seat_selection_credits(new_tier, new_plan),
                        monthly_charge=_seat_selection_monthly_charge(
                            new_tier, new_plan
                        ),
                        product_name=(
                            new_tier
                            and f"{new_plan.title} - {new_tier[0].name}"
                            or None
                        ),
                    ),
                ],
                metadata=metadata,
                **kwargs,
            )

            if new_plan == PricingPlan.TEAM and new_tier:
                set_workspace_subscription(
                    workspace=workspace,
                    plan=new_plan,
                    provider=PaymentProvider.STRIPE,
                    external_id=workspace.subscription.external_id,
                    amount=_seat_selection_credits(new_tier, new_plan),
                    charged_amount=(
                        _seat_selection_monthly_charge(new_tier, new_plan) * 100
                    ),
                    seats=new_tier[1],
                    cancel_old=False,
                )
                _apply_default_team_seat_type_to_members(workspace, new_tier)

            raise gui.RedirectException(
                get_app_route_url(payment_processing_route), status_code=303
            )

        case PaymentProvider.PAYPAL:
            if not new_plan.supports_paypal():
                gui.error(f"Paypal subscription not available for {new_plan}")

            subscription = paypal.Subscription.retrieve(
                workspace.subscription.external_id
            )
            paypal_plan_info = new_plan.get_paypal_plan()
            approval_url = subscription.update_plan(
                plan_id=paypal_plan_info["plan_id"],
                plan=paypal_plan_info["plan"],
            )
            raise gui.RedirectException(approval_url, status_code=303)

        case _:
            gui.error("Not implemented for this payment provider")


def payment_provider_radio(**props) -> str | None:
    with gui.div(className="d-flex"):
        gui.write("###### Pay Via", className="d-block me-3")
        return gui.radio(
            "",
            options=PaymentProvider.names,
            format_func=lambda name: f'<span class="me-3">{PaymentProvider[name].label}</span>',
            **props,
        )


def render_addon_section(
    workspace: "Workspace", selected_payment_provider: PaymentProvider
):
    if workspace.subscription:
        gui.write("# Purchase More Credits")
    else:
        gui.write("# Purchase Credits")
    gui.caption(f"Buy more credits. $1 per {settings.ADDON_CREDITS_PER_DOLLAR} credits")

    if workspace.subscription and workspace.subscription.payment_provider:
        provider = PaymentProvider(workspace.subscription.payment_provider)
    else:
        provider = selected_payment_provider
    match provider:
        case PaymentProvider.STRIPE:
            render_stripe_addon_buttons(workspace)
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


def render_stripe_addon_buttons(workspace: "Workspace"):
    if not (workspace.subscription and workspace.subscription.payment_provider):
        save_pm = gui.checkbox(
            "Save payment method for future purchases & auto-recharge", value=True
        )
    else:
        save_pm = True

    for dollat_amt in settings.ADDON_AMOUNT_CHOICES:
        render_stripe_addon_button(dollat_amt, workspace, save_pm)


def render_stripe_addon_button(dollat_amt: int, workspace: "Workspace", save_pm: bool):
    ref = gui.use_confirm_dialog(
        key=f"addon-confirm-dialog-{dollat_amt}", close_on_confirm=False
    )

    if gui.button(
        key=f"addon-button-{dollat_amt}", label=f"${dollat_amt:,}", type="primary"
    ):
        if (
            workspace.subscription
            and workspace.subscription.stripe_get_default_payment_method()
        ):
            ref.set_open(True)
        else:
            stripe_addon_checkout_redirect(workspace, dollat_amt, save_pm)
            return

    if not ref.is_open:
        return

    if ref.pressed_confirm:
        gui.session_state["processing-payment"] = True

    if not gui.session_state.get("processing-payment"):
        gui.confirm_dialog(
            ref=ref,
            modal_title="#### Purchase Credits",
            modal_content=f"""
Please confirm your purchase of **{dollat_amt * settings.ADDON_CREDITS_PER_DOLLAR:,} Credits for ${dollat_amt}**.

This is a one-time purchase and your account will be credited once the payment is made.
            """,
            confirm_label="Buy",
        )
        return

    header, body, footer = gui.modal_scaffold()
    with header:
        gui.write("#### Purchase Credits")
    with body, gui.center():
        html_spinner("Processing Payment...")
        success = gui.run_in_thread(
            workspace.subscription.stripe_attempt_addon_purchase,
            args=[dollat_amt],
            placeholder="",
        )
        if success is None:
            # thread is running
            return

    ref.set_open(False)
    gui.session_state.pop("processing-payment", None)

    if success:
        # close dialog
        raise gui.RerunException()
    else:
        # fallback to stripe checkout flow if the auto payment failed
        stripe_addon_checkout_redirect(workspace, dollat_amt, save_pm)


def stripe_addon_checkout_redirect(
    workspace: "Workspace", dollat_amt: int, save_pm: bool
):
    from routers.account import account_route
    from routers.account import payment_processing_route

    line_item = available_subscriptions["addon"]["stripe"].copy()
    line_item["quantity"] = dollat_amt * settings.ADDON_CREDITS_PER_DOLLAR
    kwargs = {}
    if save_pm:
        kwargs["payment_intent_data"] = {"setup_future_usage": "on_session"}
    else:
        kwargs["saved_payment_method_options"] = {"payment_method_save": "enabled"}
    checkout_session = stripe.checkout.Session.create(
        line_items=[line_item],
        mode="payment",
        success_url=get_app_route_url(payment_processing_route),
        cancel_url=get_app_route_url(account_route),
        customer=workspace.get_or_create_stripe_customer(),
        invoice_creation={"enabled": True},
        allow_promotion_codes=True,
        **kwargs,
    )
    raise gui.RedirectException(checkout_session.url, status_code=303)


def render_stripe_subscription_button(
    label: str,
    *,
    workspace: "Workspace",
    plan: PricingPlan,
    tier: SeatSelection | None = None,
    pressed: bool = False,
):
    if not plan.supports_stripe():
        gui.write("Stripe subscription not available")
        return

    # Get pricing based on tier
    monthly_charge = _seat_selection_monthly_charge(tier, plan)
    credits = _seat_selection_credits(tier, plan)

    ref = gui.use_confirm_dialog(key=f"--change-sub-confirm-dialog-{plan.key}")

    if gui.button(label, key=f"--change-sub-{plan.key}", type="primary") or pressed:
        if (
            workspace.subscription
            and workspace.subscription.stripe_get_default_payment_method()
        ):
            ref.set_open(True)
        else:
            stripe_subscription_create(workspace=workspace, plan=plan, tier=tier)

    if ref.is_open:
        gui.confirm_dialog(
            ref=ref,
            modal_title="#### Upgrade Plan",
            confirm_label="Buy",
            modal_content=f"""
Are you sure you want to subscribe to **{plan.title} (${monthly_charge}/month)**?

This will charge you the full amount today, and every month thereafter.

**{credits:,} credits** will be added to your account.
            """,
        )

    if ref.pressed_confirm:
        stripe_subscription_create(workspace=workspace, plan=plan, tier=tier)


def stripe_subscription_create(
    workspace: "Workspace",
    plan: PricingPlan,
    tier: SeatSelection | None = None,
):
    from routers.account import account_route
    from routers.account import payment_processing_route

    if workspace.subscription and workspace.subscription.is_paid():
        # sanity check: already subscribed to some plan
        gui.rerun()

    # check for existing subscriptions on stripe
    customer = workspace.get_or_create_stripe_customer()
    for sub in stripe.Subscription.list(
        customer=customer, status="active", limit=1
    ).data:
        StripeWebhookHandler.handle_subscription_updated(workspace, sub)
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )

    # try to directly create the subscription without checkout
    pm = (
        workspace.subscription
        and workspace.subscription.stripe_get_default_payment_method()
    )
    metadata = {
        settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: plan.key,
        "seats": str(tier[1]) if tier else "1",
    }
    line_items = [
        plan.get_stripe_line_item(
            credits=_seat_selection_credits(tier, plan),
            monthly_charge=_seat_selection_monthly_charge(tier, plan),
            product_name=tier and f"{plan.title} - {tier[0].name}" or None,
        )
    ]
    if pm:
        sub = stripe.Subscription.create(
            customer=pm.customer,
            items=line_items,
            metadata=metadata,
            default_payment_method=pm.id,
            proration_behavior="none",
        )
        if sub.status != "incomplete":
            # if the call succeeded redirect, otherwise use the checkout flow
            raise gui.RedirectException(
                get_app_route_url(payment_processing_route), status_code=303
            )

    # redirect to stripe checkout flow
    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        success_url=get_app_route_url(payment_processing_route),
        cancel_url=get_app_route_url(account_route),
        allow_promotion_codes=True,
        customer=customer,
        line_items=line_items,
        metadata=metadata,
        subscription_data={"metadata": metadata},
        saved_payment_method_options={"payment_method_save": "enabled"},
    )
    raise gui.RedirectException(checkout_session.url, status_code=303)


def render_paypal_subscription_button(
    *,
    plan: PricingPlan,
):
    if not plan.supports_paypal():
        gui.write("Paypal subscription not available")
        return

    lookup_key = plan.key
    gui.html(
        f"""
    <div id="paypal-subscription-{lookup_key}"
         class="paypal-subscription-{lookup_key} paypal-subscription-buttons"
         data-plan-key="{lookup_key}"></div>
    <div id="paypal-result-message"></div>
    """
    )


def render_payment_information(workspace: "Workspace"):
    if not workspace.subscription:
        return

    pm_summary = gui.run_in_thread(
        workspace.subscription.get_payment_method_summary, cache=True
    )
    if not pm_summary:
        return

    gui.write("## Payment Information", id="payment-information", className="d-block")
    with gui.div(className="ps-1"):
        col1, col2, col3 = gui.columns(3, responsive=False)
        with col1:
            gui.write("**Pay via**")
        with col2:
            provider = PaymentProvider(
                workspace.subscription.payment_provider or PaymentProvider.STRIPE
            )
            gui.write(provider.label)
        with col3:
            if gui.button(
                f"{icons.edit} Edit", type="link", key="manage-payment-provider"
            ):
                raise gui.RedirectException(
                    workspace.subscription.get_external_management_url()
                )

        pm_summary = PaymentMethodSummary(*pm_summary)
        if pm_summary.card_brand:
            col1, col2, col3 = gui.columns(3, responsive=False)
            with col1:
                gui.write("**Payment Method**")
            with col2:
                if pm_summary.card_last4:
                    gui.write(
                        f"{format_card_brand(pm_summary.card_brand)} ending in {pm_summary.card_last4}",
                        unsafe_allow_html=True,
                    )
                else:
                    gui.write(pm_summary.card_brand)
            with col3:
                if gui.button(
                    f"{icons.edit} Edit", type="link", key="edit-payment-method"
                ):
                    change_payment_method(workspace)

        if pm_summary.billing_email:
            col1, col2, _ = gui.columns(3, responsive=False)
            with col1:
                gui.write("**Billing Email**")
            with col2:
                gui.html(pm_summary.billing_email)

    from routers.account import payment_processing_route

    ref = gui.use_confirm_dialog(key="--delete-payment-method")
    gui.button_with_confirm_dialog(
        ref=ref,
        trigger_label="Delete & Cancel Subscription",
        trigger_className="border-danger text-danger",
        modal_title="#### Delete Payment Information",
        modal_content="""
Are you sure you want to delete your payment information?

This will cancel your subscription and remove your saved payment method.
        """,
        confirm_label="Delete",
        confirm_className="border-danger bg-danger text-white",
    )
    if ref.pressed_confirm:
        set_workspace_subscription(
            workspace=workspace,
            plan=PricingPlan.STARTER,
            provider=None,
            external_id=None,
            seats=1,
        )
        pm = (
            workspace.subscription
            and workspace.subscription.stripe_get_default_payment_method()
        )
        if pm:
            pm.detach()
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )


def change_payment_method(workspace: "Workspace"):
    from routers.account import payment_processing_route
    from routers.account import account_route

    match workspace.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            session = stripe.checkout.Session.create(
                mode="setup",
                currency="usd",
                customer=workspace.get_or_create_stripe_customer(),
                setup_intent_data={
                    "metadata": {"subscription_id": workspace.subscription.external_id},
                },
                success_url=get_app_route_url(payment_processing_route),
                cancel_url=get_app_route_url(account_route),
            )
            raise gui.RedirectException(session.url, status_code=303)
        case _:
            gui.error("Not implemented for this payment provider")


def format_card_brand(brand: str) -> str:
    return icons.card_icons.get(brand.lower(), brand.capitalize())


def render_billing_history(workspace: "Workspace", limit: int = 50):
    import pandas as pd

    txns = AppUserTransaction.objects.filter(
        workspace=workspace, amount__gt=0
    ).order_by("-created_at")
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


def render_auto_recharge_section(workspace: "Workspace"):
    assert workspace.subscription
    subscription = workspace.subscription

    gui.write("## Auto Recharge & Limits")
    with gui.div(className="h4"):
        auto_recharge_enabled = gui.checkbox(
            "Enable auto recharge",
            value=subscription.auto_recharge_enabled,
        )

    if auto_recharge_enabled != subscription.auto_recharge_enabled:
        subscription.auto_recharge_enabled = auto_recharge_enabled
        subscription.full_clean()
        subscription.save(update_fields=["auto_recharge_enabled"])

    if not auto_recharge_enabled:
        gui.caption(
            "Enable auto recharge to automatically keep your credit balance topped up."
        )
        return

    col1, col2 = gui.columns(2)
    with col1, gui.div(className="mb-2"):
        subscription.auto_recharge_topup_amount = gui.selectbox(
            "###### Automatically purchase",
            options=settings.ADDON_AMOUNT_CHOICES,
            format_func=lambda amt: f"{settings.ADDON_CREDITS_PER_DOLLAR * int(amt):,} credits for ${amt}",
            value=subscription.auto_recharge_topup_amount,
        )
        subscription.auto_recharge_balance_threshold = gui.selectbox(
            "###### when balance falls below",
            options=settings.AUTO_RECHARGE_BALANCE_THRESHOLD_CHOICES,
            format_func=lambda c: f"{c:,} credits",
            value=subscription.auto_recharge_balance_threshold,
        )

    with col2:
        gui.write("###### Monthly Recharge Budget")
        gui.caption(
            """
            If your account exceeds this budget in a given calendar month,
            subsequent runs & API requests will be rejected.
            """,
        )
        with gui.div(className="d-flex align-items-center"):
            subscription.monthly_spending_budget = gui.number_input(
                "",
                min_value=10,
                value=subscription.monthly_spending_budget,
                key="monthly-spending-budget",
            )
            gui.write("USD", className="d-block ms-2")

        gui.write("###### Email Notification Threshold")
        gui.caption(
            """
            If your account purchases exceed this threshold in a given
            calendar month, you will receive an email notification.
            """
        )
        with gui.div(className="d-flex align-items-center"):
            subscription.monthly_spending_notification_threshold = gui.number_input(
                "",
                min_value=10,
                value=subscription.monthly_spending_notification_threshold,
                key="monthly-spending-notification-threshold",
            )
            gui.write("USD", className="d-block ms-2")

    if gui.button("Save", type="primary", key="save-auto-recharge-and-limits"):
        try:
            subscription.full_clean()
        except ValidationError as e:
            gui.error(str(e))
        else:
            subscription.save()
            gui.success("Settings saved!")


def left_and_right(*, className: str = "", **props):
    className += " d-flex flex-row justify-content-between align-items-center"
    with gui.div(className=className, **props):
        return gui.div(), gui.div()
