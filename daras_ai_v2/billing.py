import typing
from datetime import datetime
from functools import partial

import gooey_gui as gui
import sentry_sdk
import stripe
from django.contrib.humanize.templatetags.humanize import ordinal
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import ngettext
from loguru import logger

from app_users.models import (
    AppUser,
    AppUserTransaction,
    PaymentProvider,
    TransactionReason,
)
from daras_ai_v2 import icons, settings, paypal
from daras_ai_v2.fastapi_tricks import get_app_route_url, get_route_path
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.html_spinner_widget import html_spinner
from daras_ai_v2.settings import templates
from daras_ai_v2.user_date_widgets import render_local_date_attrs
from payments.models import PaymentMethodSummary, SeatType, Subscription
from payments.plans import PricingPlan
from payments.webhooks import StripeWebhookHandler
from scripts.migrate_existing_subscriptions import available_subscriptions
from widgets.author import render_author_from_workspace
from workspaces.models import Workspace, WorkspaceRole
from workspaces.widgets import open_create_workspace_popup_js, set_current_workspace


rounded_border = "w-100 border shadow-sm rounded p-3"
SeatSelection = tuple[SeatType, int]

SEAT_COUNT_OPTIONS = [2, 3, 4, 5, 10, 15, 20, 25, 50]


def _get_team_tier_upgrade_prorated_amount(
    workspace: Workspace,
    new_plan: PricingPlan,
    new_selection: SeatSelection,
) -> int | None:
    """Preview the prorated charge (USD) for a TEAM→TEAM tier upgrade via stripe.Invoice.upcoming."""
    sub = workspace.subscription
    if not sub or sub.payment_provider != PaymentProvider.STRIPE or not sub.external_id:
        return None
    try:
        stripe_sub = stripe.Subscription.retrieve(
            sub.external_id, expand=["items", "customer"]
        )
        new_seat_type, new_seat_count = new_selection
        preview = stripe.Invoice.upcoming(
            customer=stripe_sub["customer"],
            subscription=stripe_sub.id,
            subscription_items=[
                *(
                    {"id": item.id, "deleted": True}
                    for item in stripe_sub["items"].data
                ),
                new_plan.get_stripe_line_item(
                    seat_type=new_seat_type, seat_count=new_seat_count
                ),
            ],
            subscription_proration_behavior="always_invoice",
        )
        return max(0, int(preview["amount_due"])) // 100
    except Exception as e:
        logger.warning(f"Failed to preview prorated invoice: {e}")
        return None


def _get_workspace_seat_options(plan: PricingPlan) -> dict[int, SeatType]:
    qs = SeatType.objects.filter(is_public=True, plan=plan.db_value).order_by(
        "monthly_charge"
    )
    return {seat_type.id: seat_type for seat_type in qs}


def _get_scheduled_downgrade_info(subscription_model) -> dict[str, typing.Any]:
    if (
        not subscription_model
        or subscription_model.payment_provider != PaymentProvider.STRIPE
        or not subscription_model.external_id
    ):
        return {}

    stripe_sub = stripe.Subscription.retrieve(subscription_model.external_id)

    current_period_end = stripe_sub.get("current_period_end")
    if not current_period_end:
        return {}
    if stripe_sub.get("cancel_at_period_end"):
        return dict(
            plan_title=PricingPlan.STARTER.title,
            plan_db_value=PricingPlan.STARTER.db_value,
            effective_date=datetime.fromtimestamp(current_period_end).strftime(
                "%d %b %Y"
            ),
        )

    schedule_id = stripe_sub.get("schedule")
    if not schedule_id:
        return {}

    schedule = stripe.SubscriptionSchedule.retrieve(
        schedule_id, expand=["phases.items.price.product"]
    )

    for phase in schedule.get("phases", []):
        start_date = phase.get("start_date")
        if not start_date or start_date < current_period_end:
            continue

        phase_items = phase.get("items") or []
        if not phase_items:
            continue

        plan_key = phase.get("metadata", {}).get(
            settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD, None
        )
        if not plan_key:
            continue

        plan = PricingPlan.get_by_key(plan_key)
        total_charge_cents = 0
        credits = 0
        seat_counts = {}

        for item in phase_items:
            price = item.get("price")
            quantity = int(item.get("quantity") or 0)

            if plan == PricingPlan.TEAM and price and price.product:
                seat_type_key = price.product.get("metadata", {}).get(
                    settings.STRIPE_ITEM_SEAT_TYPE_METADATA_FIELD
                )
                seat_counts.setdefault(seat_type_key, 0)
                seat_counts[seat_type_key] += quantity
            else:
                credits += quantity

            total_charge_cents += float(price.get("unit_amount_decimal")) * quantity

            return dict(
                plan_title=plan.title,
                plan_db_value=plan.db_value,
                total_monthly_charge=round(total_charge_cents / 100),
                credits=credits,
                seat_counts=seat_counts,
                effective_date=datetime.fromtimestamp(start_date).strftime("%d %b %Y"),
            )

    return {}


def _schedule_plan_change_next_cycle(
    *,
    stripe_sub: stripe.Subscription,
    new_plan: PricingPlan,
    new_selection: SeatSelection | None = None,
):
    if new_plan in [PricingPlan.TEAM, PricingPlan.PRO]:
        assert new_selection is not None, (
            "Seat selection must be provided when changing team/pro plan"
        )
        seat_type, seat_count = new_selection
    else:
        seat_type, seat_count = None, 1

    new_metadata = dict(stripe_sub.metadata or {})
    new_metadata[settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD] = new_plan.key

    schedule = stripe.SubscriptionSchedule.create(
        from_subscription=stripe_sub.id, expand=["phases.items.price"]
    )
    current_phase = (schedule.get("phases") or [None])[0]
    assert current_phase is not None, "Subscription schedule missing current phase"

    stripe.SubscriptionSchedule.modify(
        schedule.id,
        end_behavior="release",
        proration_behavior="none",
        phases=[
            dict(
                start_date=current_phase.start_date,
                end_date=current_phase.end_date,
                items=current_phase["items"],
                metadata=current_phase.metadata,
                proration_behavior="none",
            ),
            dict(
                start_date=current_phase.end_date,
                items=[
                    new_plan.get_stripe_line_item(
                        seat_type=seat_type, seat_count=seat_count
                    )
                ],
                metadata=new_metadata,
                proration_behavior="none",
            ),
        ],
    )


def clear_pending_stripe_subscription_changes(subscription: stripe.Subscription):
    # check for pending downgrade
    schedule = subscription.get("schedule")
    if isinstance(schedule, dict):
        schedule_id = schedule.get("id")
    else:
        schedule_id = schedule

    if schedule_id:
        stripe.SubscriptionSchedule.release(schedule_id)

    # check for pending cancellation
    if subscription.get("cancel_at_period_end"):
        stripe.Subscription.modify(subscription.id, cancel_at_period_end=False)


def billing_page(
    workspace: Workspace, user: AppUser, session: dict, plans_tab: str | None = None
):
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
            workspace, user=user, session=session, plans_tab=plans_tab
        )

    with gui.div(className="mb-5"):
        render_addon_section(workspace, selected_payment_provider)

    if workspace.subscription:
        if (
            workspace.subscription.payment_provider == PaymentProvider.STRIPE
            and workspace.subscription.plan != PricingPlan.TEAM.db_value
        ):
            with gui.div(className="mb-5"):
                render_auto_recharge_section(workspace)

        with gui.div(className="mb-5"):
            render_payment_information(workspace)

    with gui.div(className="mb-5"):
        render_billing_history(workspace, current_user=user)


def render_payments_setup():
    from routers.account import payment_processing_route

    gui.html(
        templates.get_template("payment_setup.html").render(
            settings=settings,
            payment_processing_url=get_app_route_url(payment_processing_route),
        )
    )


def render_current_plan(workspace: Workspace):
    plan = PricingPlan.from_sub(workspace.subscription)
    assert workspace.subscription is not None and plan is not PricingPlan.ENTERPRISE

    seat_type = workspace.subscription.get_seat_type()
    seat_count = max(1, workspace.subscription.billed_seats().count())

    monthly_charge = (
        workspace.subscription.charged_amount // 100
        or plan.get_active_monthly_charge(seat_type=seat_type, seat_count=seat_count)
    )

    if workspace.subscription.payment_provider:
        provider = PaymentProvider(workspace.subscription.payment_provider)
    else:
        provider = None

    with gui.div(className=f"{rounded_border} border-dark"):
        # ROW 1: Plan title and next invoice date
        left, right = left_and_right(className="align-items-start")
        with left:
            gui.write(
                f'#### <span class="text-muted">Current Plan:</span> {plan.title}',
                className="no-margin",
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

        # ROW 2: Plan pricing details
        left, right = left_and_right(className="align-items-start mt-3 mt-md-5 gap-5")
        with left, gui.div(className="d-flex gap-1 align-items-baseline d-md-block"):
            if plan.pricing_title:
                gui.write(plan.pricing_title, className="no-margin text-nowrap")
            else:
                gui.write(
                    f"# ${monthly_charge:,}/month", className="no-margin text-nowrap"
                )

            if monthly_charge and provider:
                gui.caption(
                    f" via **{provider.label}**", className="text-muted no-margin"
                )

        with (
            right,
            gui.div(className="text-md-end mt-3 mt-md-0"),
        ):
            if plan == PricingPlan.TEAM:
                _render_seat_info_for_team_subscription(workspace.subscription)
            else:
                credits = (
                    workspace.subscription
                    and workspace.subscription.amount
                    or plan.credits
                )
                gui.write(f"# {credits:,} credits", className="no-margin")

                if monthly_charge:
                    gui.caption(
                        f"**${monthly_charge:,}** monthly renewal for {credits:,} credits",
                        className="text-muted no-margin",
                    )

        scheduled_downgrade = gui.run_in_thread(
            _get_scheduled_downgrade_info,
            args=[workspace.subscription],
            cache=True,
            placeholder="",
            key=f"run_in_thread/scheduled_downgrade/{workspace.subscription.id}",
        )
        if scheduled_downgrade:
            _render_scheduled_downgrade_warning(
                scheduled_downgrade, className="mt-5 mb-0"
            )


def _render_scheduled_downgrade_warning(
    downgrade_info: dict[str, typing.Any],
    *,
    className: str = "",
):
    next_plan = PricingPlan.from_db_value(downgrade_info["plan_db_value"])
    effective_date = downgrade_info["effective_date"]

    if next_plan == PricingPlan.STARTER:
        change_text = f"Your plan will be cancelled on {effective_date}."
    elif next_plan == PricingPlan.TEAM:
        seat_counts = downgrade_info["seat_counts"]
        seat_type_objs = {
            st.key: st for st in SeatType.objects.filter(key__in=seat_counts.keys())
        }
        parts = [
            f"{count} {seat_type_objs[key].name} seat{'s' if count != 1 else ''} "
            f"(with up to {seat_type_objs[key].monthly_credit_limit:,} credits/seat/month)"
            for key, count in seat_counts.items()
            if key in seat_type_objs
        ]
        total_monthly = downgrade_info["total_monthly_charge"]
        change_text = (
            f"Your plan will change to {' + '.join(parts)} "
            f"on {effective_date} "
            f"with a new total price of ${total_monthly:,}/month."
        )
    else:
        total_monthly = downgrade_info["total_monthly_charge"]
        credits = downgrade_info["credits"]
        change_text = (
            f"Your plan will change to **{next_plan.title}** "
            f"(with {credits:,} pooled credits/month) "
            f"on {effective_date} "
            f"with a new total price of ${total_monthly:,}/month."
        )

    with gui.div(className=f"alert alert-warning {className}"):
        gui.write(
            f"{icons.alert} {change_text}",
            unsafe_allow_html=True,
            className="container-margin-reset",
        )


def _render_seat_info_for_team_subscription(subscription: Subscription):
    seats_qs = subscription.seats.select_related("seat_type").filter(
        seat_type__is_public=True
    )
    seat_counts = {}
    for seat in seats_qs:
        seat_counts[seat.seat_type] = seat_counts.get(seat.seat_type, 0) + 1

    seat_title = " + ".join(
        f'<span class="d-inline-block">{count} {seat_type.name}</span>'
        for seat_type, count in seat_counts.items()
    )
    gui.write(
        f"# {seat_title} seats",
        className="no-margin",
        unsafe_allow_html=True,
    )

    seat_descriptions = "\n".join(
        f"Up to {seat_type.monthly_credit_limit:,} credits/month for **${seat_type.monthly_charge}** per {seat_type.name} seat"
        for seat_type in seat_counts.keys()
    )
    gui.caption(seat_descriptions, className="text-muted no-margin")


def render_credit_balance(workspace: Workspace):
    plan = PricingPlan.from_sub(workspace.subscription)
    if not workspace.is_personal and (
        plan == PricingPlan.TEAM
        or (plan == PricingPlan.STARTER and workspace.balance <= 0)
    ):
        # for team workspaces who have not paid earlier, only
        # team (per-seat) plan is applicable
        return None

    gui.write(f"## Credit Balance: {workspace.balance:,}")
    gui.caption(
        "Every time you submit a workflow or make an API call, we deduct credits from your account."
    )


def render_all_plans(
    workspace: Workspace, user: AppUser, session: dict, plans_tab: str | None = None
) -> PaymentProvider:
    if workspace.subscription and workspace.subscription.payment_provider:
        selected_payment_provider = PaymentProvider(
            workspace.subscription.payment_provider
        )
    else:
        selected_payment_provider = PaymentProvider.STRIPE

    gui.write("## Plans")

    if workspace.is_personal:
        _render_all_plans_personal(
            workspace, user, session, selected_payment_provider, plans_tab=plans_tab
        )
    else:
        _render_all_plans_team(workspace, user, session, selected_payment_provider)

    with gui.div(className="my-2 d-flex justify-content-center"):
        gui.caption(
            f"**[See all features & benefits]({settings.PRICING_DETAILS_URL})** • Prices don’t include taxes",
        )

    return selected_payment_provider


def _render_plan_grid(
    plans: list[PricingPlan],
    workspace: Workspace,
    user: AppUser,
    session: dict,
    selected_payment_provider: PaymentProvider,
):
    partial_fn = partial(
        _render_plan,
        workspace=workspace,
        user=user,
        session=session,
        selected_payment_provider=selected_payment_provider,
    )
    with gui.div(className="mb-1"):
        grid_layout(min(len(plans), 3), plans, partial_fn, separator=False)


def _render_all_plans_personal(
    workspace: Workspace,
    user: AppUser,
    session: dict,
    selected_payment_provider: PaymentProvider,
    plans_tab: str | None = None,
):
    from gooey_gui import core

    team_plans = [PricingPlan.TEAM, PricingPlan.ENTERPRISE]
    personal_plans = [
        p for p in PricingPlan if not p.deprecated and p not in team_plans
    ]

    labels = ["Individual", "Team and Enterprise"]
    default_index = 1 if plans_tab == "team" else 0
    parent = core.RenderTreeNode(
        name="tabs",
        props=dict(defaultIndex=default_index),
        children=[
            core.RenderTreeNode(name="tab", props=dict(label=label)) for label in labels
        ],
    ).mount()
    personal_tab, team_tab = [core.NestingCtx(child) for child in parent.children]

    with personal_tab:
        _render_plan_grid(
            personal_plans,
            workspace=workspace,
            user=user,
            session=session,
            selected_payment_provider=selected_payment_provider,
        )
    with team_tab:
        _render_plan_grid(
            team_plans,
            workspace=workspace,
            user=user,
            session=session,
            selected_payment_provider=selected_payment_provider,
        )


def _render_all_plans_team(
    workspace: Workspace,
    user: AppUser,
    session: dict,
    selected_payment_provider: PaymentProvider,
):
    team_plans = [PricingPlan.TEAM, PricingPlan.ENTERPRISE]
    _render_plan_grid(
        team_plans,
        workspace=workspace,
        user=user,
        session=session,
        selected_payment_provider=selected_payment_provider,
    )


def _render_plan(
    plan: PricingPlan,
    workspace: Workspace,
    user: AppUser,
    session: dict,
    selected_payment_provider: PaymentProvider,
):
    current_plan = PricingPlan.from_sub(workspace.subscription)

    if plan == current_plan or (
        plan == PricingPlan.TEAM
        and current_plan != PricingPlan.ENTERPRISE
        and not workspace.is_personal
    ):
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
        seat_selection = _render_plan_pricing(
            plan, selected_payment_provider, workspace
        )
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
                seat_selection=seat_selection,
            )


def _render_plan_details(plan: PricingPlan):
    """Render plan details."""
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
    plan: PricingPlan, payment_provider: PaymentProvider | None, workspace: Workspace
) -> SeatSelection | None:
    pricing_div = gui.div(className="container-margin-reset")

    if plan in [PricingPlan.TEAM, PricingPlan.PRO]:
        seat_selection = _render_seat_selection(plan=plan, workspace=workspace)
    else:
        seat_selection = None

    with pricing_div:
        if seat_selection:
            seat_type, seat_count = seat_selection
        else:
            seat_type, seat_count = None, None
        gui.write(
            f"""
            ### {plan.get_pricing_title(seat_type=seat_type, seat_count=seat_count)}
            """
        )
        if caption := plan.get_pricing_caption():
            gui.caption(caption)

    return seat_selection


def _render_seat_type_option(seat_type: SeatType, plan: PricingPlan) -> str:
    if plan == PricingPlan.PRO:
        return f"Up to {seat_type.monthly_credit_limit:,} credits/month • ${seat_type.monthly_charge:,}"
    else:
        return (
            f"{seat_type.name}"
            f" • Up to {seat_type.monthly_credit_limit:,} Cr / month"
            f" • ${seat_type.monthly_charge}"
        )


def _render_seat_selection(plan: PricingPlan, workspace: Workspace) -> SeatSelection:
    if (
        workspace.subscription
        and workspace.subscription.plan == plan.db_value
        and workspace.subscription.is_paid()
    ):
        current_seat_type = workspace.subscription.get_seat_type()
    else:
        current_seat_type = None

    seat_options = _get_workspace_seat_options(plan)
    assert seat_options, f"No seat options found for plan {plan.title}"

    colspec = [3, 1] if plan == PricingPlan.TEAM else [12, 0]
    col1, col2 = gui.columns(colspec, responsive=True)
    with col1:
        label = "Monthly credits"
        if plan == PricingPlan.TEAM:
            label += " per member"
        seat_type_id = gui.selectbox(
            label=label,
            options=seat_options,
            format_func=lambda seat_id: _render_seat_type_option(
                seat_options[seat_id], plan=plan
            ),
            key=f"seat-type-select-{plan.key}",
            value=(current_seat_type and current_seat_type.id),
            className="mb-0 container-margin-reset",
        )
        selected_seat_type = seat_options[seat_type_id]

    if plan == PricingPlan.TEAM:
        default_seat_count = (
            workspace.subscription
            and workspace.subscription.billed_seats().count()
            or max(workspace.used_seats, 1)
        )
        if (
            default_seat_count not in SEAT_COUNT_OPTIONS
            and default_seat_count < SEAT_COUNT_OPTIONS[-1]
        ):
            default_seat_count = next(
                c for c in SEAT_COUNT_OPTIONS if c > default_seat_count
            )

        with col2:
            count = gui.selectbox(
                label="Seats",
                options=SEAT_COUNT_OPTIONS,
                key=f"seat-count-select-{plan.key}-{workspace.id}",
                value=default_seat_count,
                className="mb-0 container-margin-reset",
            )
    else:
        count = 1

    return selected_seat_type, count


def _render_plan_action_button(
    *,
    workspace: Workspace,
    user: AppUser,
    plan: PricingPlan,
    payment_provider: PaymentProvider | None,
    session: dict,
    seat_selection: SeatSelection | None = None,
):
    from routers.account import members_route

    current_plan = PricingPlan.from_sub(workspace.subscription)
    current_seat_type = (
        workspace.subscription and workspace.subscription.get_seat_type()
    )
    current_seats = (
        workspace.subscription
        and max(1, workspace.subscription.billed_seats().count())
        or 1
    )
    current_seat_selection = (
        current_seat_type and (current_seat_type, current_seats) or None
    )

    if plan == current_plan and (
        plan not in [PricingPlan.TEAM, PricingPlan.PRO]
        or (
            workspace.subscription
            and seat_selection
            and current_seat_selection == seat_selection
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

    elif (
        plan == PricingPlan.TEAM
        and seat_selection
        and seat_selection[1] < workspace.used_seats
    ):
        min_allowed_seat_count = next(
            (c for c in SEAT_COUNT_OPTIONS if c >= workspace.used_seats),
            SEAT_COUNT_OPTIONS[-1],
        )

        with gui.div(className="d-flex p-3 pb-0 gap-2 alert alert-danger text-black"):
            # fire emoji
            gui.write("🔥")
            with gui.div():
                gui.write(
                    f"""
                    You currently have {workspace.used_seats} members in your team.
                    Please select a plan with at least {workspace.used_seats} seats or remove some members.
                    """
                )
                with gui.div(className="d-flex align-items-center gap-2"):
                    if gui.button(
                        f"Stay at {min_allowed_seat_count} seats",
                        type="link",
                        className="fw-normal",
                    ):
                        gui.session_state[
                            f"seat-count-select-{plan.key}-{workspace.id}"
                        ] = min_allowed_seat_count
                        raise gui.RerunException()
                    gui.write("|")
                    gui.write(
                        f"""
                        [Remove Members]({get_route_path(members_route)})
                        """
                    )

    elif workspace.subscription and workspace.subscription.is_paid():
        render_change_subscription_button(
            workspace=workspace, plan=plan, seat_selection=seat_selection
        )

    else:
        assert payment_provider is not None
        _render_create_subscription_button(
            workspace=workspace,
            plan=plan,
            payment_provider=payment_provider,
            seat_selection=seat_selection,
        )


def _render_switch_workspace_button(workspace: Workspace, user: AppUser, session: dict):
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
    workspace: Workspace,
    plan: PricingPlan,
    seat_selection: SeatSelection | None = None,
):
    # subscription exists, show upgrade/downgrade button
    if plan in [PricingPlan.TEAM, PricingPlan.PRO]:
        assert seat_selection is not None
        seat_type, seat_count = seat_selection
    else:
        seat_type, seat_count = None, 1

    current_plan = PricingPlan.from_sub(workspace.subscription)
    if current_plan in [PricingPlan.TEAM, PricingPlan.PRO]:
        current_seat_type = workspace.subscription.get_seat_type()
        current_seat_count = max(1, workspace.subscription.billed_seats().count())
    else:
        current_seat_type, current_seat_count = None, 1

    # validations:
    if plan == current_plan and seat_type and current_seat_type:
        if (
            seat_count < current_seat_count
            and seat_type.monthly_charge > current_seat_type.monthly_charge
        ):
            gui.error(
                """
                Decreasing seats and increasing monthly usage limit in the same change is not supported.
                """
            )
            return
        if (
            seat_count > current_seat_count
            and seat_type.monthly_charge < current_seat_type.monthly_charge
        ):
            gui.error(
                """
                Increasing seats and decreasing monthly usage limit in the same change is not supported.
                """
            )
            return

    current_monthly_charge = (
        workspace.subscription.charged_amount // 100
        or current_plan.get_active_monthly_charge(
            seat_type=current_seat_type, seat_count=current_seat_count
        )
    )
    new_monthly_charge = plan.get_active_monthly_charge(
        seat_type=seat_type, seat_count=seat_count
    )
    if new_monthly_charge > current_monthly_charge or current_plan.deprecated:
        _render_upgrade_subscription_button(
            workspace=workspace, plan=plan, seat_selection=seat_selection
        )
    else:
        _render_downgrade_subscription_button(
            workspace=workspace, plan=plan, seat_selection=seat_selection
        )


def _render_downgrade_subscription_button(
    *,
    workspace: Workspace,
    plan: PricingPlan,
    seat_selection: SeatSelection | None = None,
):
    current_plan = PricingPlan.from_sub(workspace.subscription)
    current_monthly_charge = (
        workspace.subscription and workspace.subscription.charged_amount // 100 or 0
    )

    selected_monthly_charge = plan.get_active_monthly_charge(
        seat_type=seat_selection and seat_selection[0] or None,
        seat_count=seat_selection and seat_selection[1] or 1,
    )

    ref = gui.use_confirm_dialog(key=f"--modal-{plan.key}")
    next_invoice_ts = (
        workspace.subscription
        and workspace.subscription.is_paid()
        and gui.run_in_thread(
            workspace.subscription.get_next_invoice_timestamp,
            cache=True,
            placeholder="",
        )
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
        change_subscription(workspace, new_plan=plan, new_selection=seat_selection)


def _render_upgrade_subscription_button(
    *,
    workspace: Workspace,
    plan: PricingPlan,
    seat_selection: SeatSelection | None = None,
):
    current_plan = PricingPlan.from_sub(workspace.subscription)
    current_seat_type = workspace.subscription.get_seat_type()

    upgrade_dialog = gui.use_confirm_dialog(
        key=f"upgrade-workspace-{workspace.id}-plan-{plan.key}-{current_seat_type}"
    )

    # Pro plan is only for personal workspaces, skip workspace creation popup
    if workspace.is_personal and plan != PricingPlan.PRO:
        if gui.button(
            "Create Team",
            type="primary",
            key=f"create-workspace-btn-{plan.key}-{workspace.id}",
            onClick=open_create_workspace_popup_js(
                selected_plan=plan, seat_selection=seat_selection
            ),
        ):
            gui.session_state["pressed_create_workspace"] = True
        return

    # For TEAM plan on team workspaces, show detailed order summary
    if plan == PricingPlan.TEAM:
        assert seat_selection is not None

        prorated_today = None
        if current_plan == PricingPlan.TEAM:
            prorated_today = _get_team_tier_upgrade_prorated_amount(
                workspace, plan, seat_selection
            )

        next_invoice_ts = gui.run_in_thread(
            workspace.subscription.get_next_invoice_timestamp, cache=True
        )
        modal_content = get_order_summary_content(
            plan,
            seat_selection,
            prorated_today=prorated_today,
            next_invoice_ts=next_invoice_ts,
        )
        confirm_label = "Upgrade"
        modal_title = "#### Order Summary"
    else:
        current_selection = (
            (
                current_seat_type,
                max(1, workspace.subscription.billed_seats().count()),
            )
            if current_seat_type
            else None
        )
        current_monthly_charge = current_plan.get_active_monthly_charge(
            seat_type=current_selection and current_selection[0] or None,
            seat_count=current_selection and current_selection[1] or 1,
        )
        new_monthly_charge = plan.get_active_monthly_charge(
            seat_type=seat_selection and seat_selection[0] or None,
            seat_count=seat_selection and seat_selection[1] or 1,
        )
        credits = plan.get_active_credits(
            seat_type=seat_selection and seat_selection[0] or None,
            seat_count=seat_selection and seat_selection[1] or 1,
        )

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
            change_subscription(workspace, new_plan=plan, new_selection=seat_selection)
        except (stripe.CardError, stripe.InvalidRequestError) as e:
            if isinstance(e, stripe.InvalidRequestError):
                sentry_sdk.capture_exception(e)
                logger.warning(e)

            # only handle error if it's related to mandates
            # cancel current subscription & redirect user to new subscription page
            workspace.subscription.cancel()
            stripe_subscription_create(workspace, plan, seat_selection=seat_selection)


def _render_create_subscription_button(
    *,
    workspace: Workspace,
    plan: PricingPlan,
    payment_provider: PaymentProvider,
    seat_selection: SeatSelection | None = None,
):
    # Pro plan is only for personal workspaces, skip workspace creation popup
    if workspace.is_personal and plan != PricingPlan.PRO:
        if gui.button(
            "Create Team",
            type="primary",
            onClick=open_create_workspace_popup_js(
                selected_plan=plan, seat_selection=seat_selection
            ),
        ):
            gui.session_state["pressed_create_workspace"] = True
    elif plan == PricingPlan.TEAM and not workspace.is_personal:
        assert seat_selection is not None

        # For TEAM plan on team workspaces, show order summary modal first
        _render_team_plan_order_summary_button(
            workspace=workspace,
            plan=plan,
            payment_provider=payment_provider,
            seat_selection=seat_selection,
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
                    seat_selection=seat_selection,
                )
            case PaymentProvider.PAYPAL:
                # PayPal doesn't support tiers, use default
                render_paypal_subscription_button(plan=plan)


def get_order_summary_content(
    plan: PricingPlan,
    seat_selection: SeatSelection,
    prorated_today: int | None = None,
    next_invoice_ts: int | None = None,
) -> str:
    from routers.account import members_route

    seat_type, seat_count = seat_selection
    total_charge = seat_type.monthly_charge * seat_count
    extra_seats = seat_count - 1

    # Build extra seats line only if there are extra seats
    if extra_seats > 0:
        extra_seats_title = (
            f"{extra_seats} extra paid {ngettext('seat', 'seats', extra_seats)} "
        )
        extra_seats_line = f"""
**{extra_seats_title:·<40} ${extra_seats * seat_type.monthly_charge}**
{extra_seats} x ${seat_type.monthly_charge}/month
[View members]({get_route_path(members_route)})
"""
    else:
        extra_seats_line = f"[View members]({get_route_path(members_route)})\n"

    plan_tier_title = f"{plan.title} {seat_type.monthly_charge} Plan "

    if prorated_today is not None:
        if next_invoice_ts:
            effective_date = datetime.fromtimestamp(next_invoice_ts).strftime("%d")
            effective_date_text = f"on the {ordinal(effective_date)} of"
        else:
            effective_date_text = ""
        charge_line = (
            f"Your payment method will be charged **${prorated_today:,}** today "
            f"(prorated) and **${total_charge:,}** {effective_date_text} every month until you cancel."
        )
    else:
        charge_line = (
            f"Your payment method will be charged **${total_charge}** today "
            "and again every month until you cancel."
        )

    return f"""
**Monthly credits per member**
{seat_type.monthly_credit_limit or 0:,} / month

**{plan_tier_title:·<40} ${seat_type.monthly_charge}**
Base of ${seat_type.monthly_charge}/month

{extra_seats_line}

**{"Total ":·<48} ${total_charge}**

---

{charge_line}
    """


def _render_team_plan_order_summary_button(
    *,
    workspace: Workspace,
    plan: PricingPlan,
    payment_provider: PaymentProvider,
    seat_selection: SeatSelection,
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
            modal_content=get_order_summary_content(plan, seat_selection),
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
                    seat_selection=seat_selection,
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
    workspace: Workspace,
    new_plan: PricingPlan,
    new_selection: SeatSelection | None = None,
    **kwargs,
) -> typing.NoReturn | None:
    from routers.account import account_route
    from routers.account import payment_processing_route

    current_plan = PricingPlan.from_sub(workspace.subscription)

    # Check if plan and seat selection are unchanged
    if current_plan in [PricingPlan.TEAM, PricingPlan.PRO]:
        current_seat_type = workspace.subscription.get_seat_type()
        current_seat_count = workspace.subscription.billed_seats().count() or 1
        current_selection = (current_seat_type, current_seat_count)
    else:
        current_selection = None

    if new_plan == current_plan and current_selection == new_selection:
        raise gui.RedirectException(get_app_route_url(account_route), status_code=303)

    if new_plan == PricingPlan.STARTER and workspace.subscription.is_paid():
        workspace.subscription.cancel(immediately=False)
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )

    match workspace.subscription.payment_provider:
        case PaymentProvider.STRIPE:
            if not new_plan.supports_stripe():
                gui.error(f"Stripe subscription not available for {new_plan}")
                return

            if workspace.subscription.charged_amount:
                current_monthly_charge = workspace.subscription.charged_amount // 100
            else:
                current_monthly_charge = current_plan.get_active_monthly_charge(
                    seat_type=current_seat_type, seat_count=current_seat_count
                )

            if new_selection:
                new_seat_type, new_seat_count = new_selection
            else:
                new_seat_type, new_seat_count = None, 1

            new_monthly_charge = new_plan.get_active_monthly_charge(
                seat_type=new_seat_type, seat_count=new_seat_count
            )

            stripe_sub = stripe.Subscription.retrieve(
                workspace.subscription.external_id,
                expand=["items", "items.data.price", "schedule"],
            )
            clear_pending_stripe_subscription_changes(stripe_sub)

            if (
                not current_plan.deprecated
                and new_monthly_charge < current_monthly_charge
            ):
                # for downgrades, schedule for next cycle
                _schedule_plan_change_next_cycle(
                    stripe_sub=stripe_sub,
                    new_plan=new_plan,
                    new_selection=new_selection,
                )
                raise gui.RedirectException(
                    get_app_route_url(payment_processing_route), status_code=303
                )

            # for upgrades, charge immediately
            if current_plan == PricingPlan.TEAM:
                # prorate for changes within Team plan
                kwargs["proration_behavior"] = "always_invoice"
                kwargs["payment_behavior"] = "error_if_incomplete"
            else:
                kwargs["proration_behavior"] = "none"
                kwargs["billing_cycle_anchor"] = "now"

            metadata = {settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: new_plan.key}
            stripe.Subscription.modify(
                stripe_sub.id,
                items=[
                    *(
                        {"id": item.id, "deleted": True}
                        for item in stripe_sub["items"].data
                    ),
                    new_plan.get_stripe_line_item(
                        seat_type=new_seat_type, seat_count=new_seat_count
                    ),
                ],
                metadata=metadata,
                **kwargs,
            )
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
    workspace: Workspace, selected_payment_provider: PaymentProvider
):
    # Check if workspace is allowed to purchase topups - hide entire section if not
    if not workspace.allow_credit_topups():
        return

    if (
        workspace.subscription
        and workspace.subscription.plan == PricingPlan.TEAM.db_value
    ):
        # add-on purchases don't make sense on team
        # workspace where credits are not pooled
        return

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


def render_stripe_addon_buttons(workspace: Workspace):
    if not (workspace.subscription and workspace.subscription.payment_provider):
        save_pm = gui.checkbox(
            "Save payment method for future purchases & auto-recharge", value=True
        )
    else:
        save_pm = True

    for dollat_amt in settings.ADDON_AMOUNT_CHOICES:
        render_stripe_addon_button(dollat_amt, workspace, save_pm)


def render_stripe_addon_button(dollat_amt: int, workspace: Workspace, save_pm: bool):
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
    workspace: Workspace, dollat_amt: int, save_pm: bool
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
    workspace: Workspace,
    plan: PricingPlan,
    seat_selection: SeatSelection | None = None,
    pressed: bool = False,
):
    if not plan.supports_stripe():
        gui.write("Stripe subscription not available")
        return

    # Get pricing based on selected seat configuration.
    monthly_charge = plan.get_active_monthly_charge(
        seat_type=seat_selection and seat_selection[0] or None,
        seat_count=seat_selection and seat_selection[1] or 1,
    )
    credits = plan.get_active_credits(
        seat_type=seat_selection and seat_selection[0] or None,
        seat_count=seat_selection and seat_selection[1] or 1,
    )

    ref = gui.use_confirm_dialog(key=f"--change-sub-confirm-dialog-{plan.key}")

    if gui.button(label, key=f"--change-sub-{plan.key}", type="primary") or pressed:
        if (
            workspace.subscription
            and workspace.subscription.stripe_get_default_payment_method()
        ):
            ref.set_open(True)
        else:
            stripe_subscription_create(
                workspace=workspace, plan=plan, seat_selection=seat_selection
            )

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
        stripe_subscription_create(
            workspace=workspace, plan=plan, seat_selection=seat_selection
        )


def stripe_subscription_create(
    workspace: Workspace,
    plan: PricingPlan,
    seat_selection: SeatSelection | None = None,
):
    from routers.account import account_route
    from routers.account import payment_processing_route

    # check for existing subscriptions on stripe
    customer = workspace.get_or_create_stripe_customer()
    for sub in stripe.Subscription.list(
        customer=customer, status="active", limit=1
    ).data:
        StripeWebhookHandler.handle_subscription_updated(workspace, sub)
        raise gui.RedirectException(
            get_app_route_url(payment_processing_route), status_code=303
        )

    if seat_selection:
        seat_type, seat_count = seat_selection
    else:
        seat_type, seat_count = None, 1

    # try to directly create the subscription without checkout
    pm = (
        workspace.subscription
        and workspace.subscription.stripe_get_default_payment_method()
    )
    metadata = {settings.STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: plan.key}
    line_items = [plan.get_stripe_line_item(seat_type=seat_type, seat_count=seat_count)]
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


def render_payment_information(workspace: Workspace):
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

    _render_delete_payment_method_button(workspace)


def _render_delete_payment_method_button(workspace: Workspace):
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
        if pm := workspace.subscription.stripe_get_default_payment_method():
            pm.detach()
        change_subscription(workspace, new_plan=PricingPlan.STARTER)


def change_payment_method(workspace: Workspace):
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


def render_billing_history(
    workspace: Workspace, current_user: AppUser, limit: int = 50
):
    import pandas as pd

    txns = (
        AppUserTransaction.objects.select_related("member")
        .filter(workspace=workspace)
        .exclude(reason=TransactionReason.DEDUCT)
        .order_by("-created_at")
    )
    if not workspace.is_personal:
        membership = workspace.memberships.filter(user=current_user).first()
        if not membership:
            return

        if WorkspaceRole(membership.role) in [WorkspaceRole.ADMIN, WorkspaceRole.OWNER]:
            # admins: exclude limit reset transactions for other members
            txns = txns.filter(Q(member__isnull=True) | Q(member=membership))
        else:
            # non-admins: should only see their own transactions
            txns = txns.filter(
                member=membership,
                reason__in=[
                    TransactionReason.MEMBER_LIMIT_RESET,
                    TransactionReason.MEMBER_SEAT_CHANGE,
                ],
            )

    if not txns:
        return

    records = []
    for txn in txns[:limit]:
        record = {
            "Date": txn.created_at.strftime("%m/%d/%Y"),
            "Description": txn.reason_note(),
            "Credits": f"+{txn.amount:,}",
            "Amount": f"-${txn.charged_amount / 100:,.2f}",
            "Balance": f"{txn.end_balance:,}",
        }
        if txn.plan == PricingPlan.TEAM.db_value:
            if txn.reason == TransactionReason.MEMBER_LIMIT_RESET:
                record.update(
                    {
                        "Credits": f"Reset to {txn.end_balance:,}",
                        "Amount": "-",
                        "Balance": f"{txn.end_balance:,}",
                    }
                )
            elif txn.reason == TransactionReason.MEMBER_SEAT_CHANGE:
                record.update(
                    {
                        "Credits": "Limit updated",
                        "Amount": "-",
                        "Balance": "-",
                    }
                )
            else:
                record.update(
                    {
                        "Credits": "-",
                        "Amount": f"-${txn.charged_amount / 100:,.2f}",
                        "Balance": "-",
                    }
                )
        records.append(record)

    gui.write("## Billing History", className="d-block")
    with gui.div(className="w-100 overflow-auto"):
        gui.table(pd.DataFrame.from_records(records))
    if txns.count() > limit:
        gui.caption(f"Showing only the most recent {limit} transactions.")


def render_auto_recharge_section(workspace: Workspace):
    assert workspace.subscription
    subscription = workspace.subscription

    # Check if workspace is allowed to use auto-recharge - hide entire section if not
    if not workspace.allow_credit_topups():
        return

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


def left_and_right(*, responsive: bool = True, className: str = "", **props):
    if responsive:
        className += " d-block d-md-flex"
    else:
        className += " d-flex"
    className += " flex-row justify-content-between"
    with gui.div(className=className, **props):
        return gui.div(), gui.div()
