from __future__ import annotations

import gooey_gui as gui
from django.db.models import Q, QuerySet
from furl import furl

from app_users.models import AppUser
from bots.models import (
    BotIntegration,
    Platform,
    PublishedRun,
    SavedRun,
)
from daras_ai_v2 import icons, settings
from daras_ai_v2.base import RecipeTabs
from daras_ai_v2.bot_integration_add import render_integrations_add, copilot_app_url
from daras_ai_v2.bot_integration_widgets import (
    broadcast_input,
    general_integration_settings,
    web_widget_config,
)
from payments.plans import PricingPlan
from workspaces.models import Workspace


def render_integrations_tab(
    *,
    user: AppUser,
    workspace: Workspace,
    saved_run: SavedRun,
    published_run: PublishedRun,
):
    gui.newline()

    # make sure the user knows that they are on a saved run not the published run
    if published_run and published_run.saved_run_id != saved_run.id:
        last_saved_url = copilot_app_url(
            current_sr=saved_run,
            current_pr=published_run,
            tab=RecipeTabs.integrations,
        )
        gui.caption(
            f"Note: You seem to have unpublished changes. Deployments use the [last saved version]({last_saved_url}), not the currently visible edits.",
            className="text-center text-muted",
        )

    # see which integrations are available to the user for the published run
    integrations_q = Q(published_run=published_run) | Q(
        saved_run__example_id=published_run.published_run_id
    )
    if not (user and user.is_admin()):
        integrations_q &= Q(workspace=workspace)

    integrations_qs: QuerySet[BotIntegration] = BotIntegration.objects.filter(
        integrations_q
    ).order_by("platform", "-created_at")

    # no connected integrations on this run
    if not (integrations_qs and integrations_qs.exists()):
        render_integrations_add(
            label="#### Connect your Copilot",
            current_sr=saved_run,
            pr=published_run,
            user=user,
            workspace=workspace,
        )
        return

    # this gets triggered on the /add route
    if gui.session_state.pop("--add-integration", None):
        render_integrations_add(
            label="#### Deploy to a New Channel",
            current_sr=saved_run,
            pr=published_run,
            user=user,
            workspace=workspace,
        )
        with gui.center():
            if gui.button("Return to Configure"):
                cancel_url = copilot_app_url(
                    current_sr=saved_run,
                    current_pr=published_run,
                    tab=RecipeTabs.integrations,
                )
                raise gui.RedirectException(cancel_url)
        return

    with gui.center():
        # signed in, can edit, and has connected botintegrations on this run
        render_integrations_settings(
            integrations=list(integrations_qs),
            user=user,
            workspace=workspace,
            current_sr=saved_run,
            current_pr=published_run,
        )


def render_integrations_settings(
    *,
    integrations: list[BotIntegration],
    user: AppUser | None,
    workspace: Workspace,
    current_sr: SavedRun,
    current_pr: PublishedRun,
) -> None:
    from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
    from recipes.QRCodeGenerator import generate_qr_code
    from routers.facebook_api import wa_connect_url

    with gui.div(className="w-100 text-start"):
        col1, col2 = gui.columns(2)

    with col1:
        gui.markdown("#### Configure your Copilot")
        gui.newline()

        if len(integrations) > 1:
            with gui.div(style=dict(width="100%", maxWidth="500px", textAlign="left")):
                integrations_map = {i.id: i for i in integrations}
                bi_id = gui.selectbox(
                    label="",
                    options=integrations_map.keys(),
                    format_func=lambda bi_id: f"{Platform(integrations_map[bi_id].platform).get_icon()} &nbsp; {integrations_map[bi_id].name}",
                    key="bi_id",
                )
                bi = integrations_map[bi_id]
                old_bi_id = gui.session_state.get("old_bi_id", bi_id)
                if bi_id != old_bi_id:
                    raise gui.RedirectException(
                        copilot_app_url(
                            current_sr=current_sr,
                            current_pr=current_pr,
                            tab=RecipeTabs.integrations,
                            path_params=dict(integration_id=bi.api_integration_id()),
                        )
                    )
                gui.session_state["old_bi_id"] = bi_id
        else:
            bi = integrations[0]

    with col2:
        test_link = bi.get_bot_test_link()
        if bi.demo_qr_code_image:
            img_src = bi.demo_qr_code_image
        elif test_link:
            img_src = generate_qr_code(test_link)
        else:
            img_src = None

        if img_src is not None:
            gui.image(img_src, style=dict(maxWidth="125px", maxHeight="125px"))

    if bi.platform == Platform.WEB:
        web_widget_config(bi=bi, user=user, hostname="gooey.ai")
        with gui.div(className="w-100"):
            gui.write("---")

    icon = Platform(bi.platform).get_icon()
    with gui.div(className="w-100 text-start"):
        col1, col2 = gui.columns(2, style=dict(alignItems="center"))
        with col1:
            if bi.extension_number:
                gui.write("###### Connected to Extension")
            else:
                gui.write("###### Connected to")

            gui.write(f"{icon} {bi}", unsafe_allow_html=True)
        with col2:
            if not test_link:
                gui.write("Message quicklink not available.")
            elif bi.platform == Platform.TWILIO:
                copy_to_clipboard_button(
                    f"{icons.copy_solid} Copy Phone Number",
                    value=test_link.lstrip("tel:"),
                    type="secondary",
                )
            else:
                copy_to_clipboard_button(
                    f"{icons.copy_solid} Copy {Platform(bi.platform).label} Link",
                    value=test_link,
                    type="secondary",
                )

            if bi.platform == Platform.FACEBOOK:
                gui.anchor(
                    '<i class="fa-regular fa-inbox"></i> Open Inbox',
                    "https://www.facebook.com/latest/inbox",
                    unsafe_allow_html=True,
                    new_tab=True,
                )

        col1, col2 = gui.columns(2, style=dict(alignItems="center"))
        with col1:
            gui.write("###### Test")
            if bi.platform == Platform.TWILIO:
                test_caption = (
                    f"Call or send a text message via {Platform(bi.platform).label}."
                )
            else:
                test_caption = f"Send a message via {Platform(bi.platform).label}."
            if bi.extension_number:
                test_caption += f" (with extension {bi.extension_number})."
            help_text = None
            if bi.platform == Platform.TWILIO:
                help_text = (
                    "**SMS:** Send `/extension <extension number>` to connect to the agent. `/disconnect` to start fresh.\n\n"
                    "**Voice Call:** ` * <extension number>` to change extension, `*#` to disconnect."
                )
            gui.caption(test_caption, help=help_text)
        with col2:
            if not test_link:
                gui.write("Message quicklink not available.")
            elif bi.platform == Platform.FACEBOOK:
                gui.anchor(
                    f"{icon} Open Profile",
                    test_link,
                    unsafe_allow_html=True,
                    new_tab=True,
                )
            elif bi.platform == Platform.TWILIO:
                gui.anchor(
                    '<i class="fa-regular fa-phone"></i> Start Voice Call',
                    test_link,
                    unsafe_allow_html=True,
                    new_tab=True,
                )
                sms_url = furl("sms:") / bi.twilio_phone_number.as_e164
                if bi.extension_number:
                    sms_url.args["body"] = f"{bi.extension_number}"
                gui.anchor(
                    '<i class="fa-regular fa-sms"></i> Send SMS',
                    str(sms_url),
                    unsafe_allow_html=True,
                    new_tab=True,
                )
            else:
                gui.anchor(
                    f"{icon} Message {bi.get_display_name()}",
                    test_link,
                    unsafe_allow_html=True,
                    new_tab=True,
                )

        if bi.platform == Platform.TELEGRAM:
            col1, col2 = gui.columns(2, style=dict(alignItems="center"))
            with col1:
                gui.write("###### Manage Bot")
                gui.caption(
                    "Open BotFather in Telegram to manage your bot's name, photo, and other settings."
                )
            with col2:
                telegram_botfather_url = furl(
                    "https://t.me/BotFather", query_params={"text": "/mybots"}
                )
                gui.anchor(
                    f"{icon} Open BotFather",
                    str(telegram_botfather_url),
                    unsafe_allow_html=True,
                    new_tab=True,
                    type="secondary",
                )

        if bi.platform == Platform.WHATSAPP and bi.extension_number:
            is_enterprise = (
                workspace.subscription
                and PricingPlan.from_sub(workspace.subscription)
                == PricingPlan.ENTERPRISE
            )

            col1, col2 = gui.columns(2, style=dict(alignItems="center"))
            with col1:
                gui.write("###### Bring your own number")
                gui.write(
                    "Connect your mobile # (that's not already on WhatsApp) with your Facebook Business Profile. [Help Guide](https://gooey.ai/docs/guides/copilot/deploy-to-whatsapp)",
                )

            with col2:
                gui.anchor(
                    "Connect number",
                    href=wa_connect_url(current_pr.id),
                    style=dict(
                        backgroundColor="#1877F2",
                        color="white",
                        width="100%",
                        maxWidth="225px",
                    ),
                    type="secondary",
                )

            gui.html("""
                    <div class="d-flex align-items-center my-2">
                        <hr class="flex-grow-1">
                        <span class="px-3 text-muted">or</span>
                        <hr class="flex-grow-1">
                    </div>
                    """)

            col1, col2 = gui.columns(2, style=dict(alignItems="center"))
            with col1:
                gui.write("###### Buy a dedicated number")
                if is_enterprise:
                    gui.write(
                        "As a premium customer, please contact us to setup a managed number"
                    )
                else:
                    gui.write(
                        f"[Upgrade]({settings.PRICING_DETAILS_URL}) for a number managed by Gooey.AI"
                    )
            with col2:
                if is_enterprise:
                    gui.anchor(
                        "Contact",
                        href=settings.CONTACT_URL,
                        style=dict(width="100%", maxWidth="225px"),
                        type="primary",
                    )
                else:
                    gui.anchor(
                        "Upgrade",
                        href=settings.PRICING_DETAILS_URL,
                        style=dict(width="100%", maxWidth="225px"),
                        type="primary",
                    )

            gui.write("---")

        if bi.platform == Platform.TWILIO and bi.extension_number:
            col1, col2 = gui.columns(2, style=dict(alignItems="center"))
            is_enterprise = (
                workspace.subscription
                and PricingPlan.from_sub(workspace.subscription)
                == PricingPlan.ENTERPRISE
            )
            with col1:
                gui.write("###### Get a Dedicated Number")
                if is_enterprise:
                    gui.write(
                        "As a premium customer, please contact us to set up a managed number"
                    )
                else:
                    gui.write(
                        f"[Upgrade]({settings.PRICING_DETAILS_URL}) for a dedicated number managed by Gooey.AI"
                    )
            with col2:
                if is_enterprise:
                    gui.anchor(
                        "Contact",
                        href=settings.CONTACT_URL,
                        style=dict(width="100%", maxWidth="225px"),
                        type="primary",
                    )
                else:
                    gui.anchor(
                        "Upgrade",
                        href=settings.PRICING_DETAILS_URL,
                        style=dict(width="100%", maxWidth="225px"),
                        type="primary",
                    )
        col1, col2 = gui.columns(2, style=dict(alignItems="center"))
        with col1:
            gui.write("###### Understand your Users")
            gui.caption("See real-time analytics.")
        with col2:
            gui.anchor(
                "📊 View Analytics",
                str(
                    furl(
                        copilot_app_url(
                            current_sr=current_sr,
                            current_pr=current_pr,
                            tab=RecipeTabs.integrations,
                            path_params=dict(integration_id=bi.api_integration_id()),
                        )
                    )
                    / "stats/"
                ),
                new_tab=True,
            )
            if (
                bi.platform == Platform.TWILIO
                and bi.twilio_phone_number_sid
                and not bi.extension_number
            ):
                gui.anchor(
                    f"{icon} Open Twilio Console",
                    str(
                        furl(
                            "https://console.twilio.com/us1/develop/phone-numbers/manage/incoming/"
                        )
                        / bi.twilio_phone_number_sid
                        / "calls"
                    ),
                    unsafe_allow_html=True,
                    new_tab=True,
                )

        if bi.platform == Platform.WHATSAPP and bi.wa_business_waba_id:
            col1, col2 = gui.columns(2, style=dict(alignItems="center"))
            with col1:
                gui.write("###### WhatsApp Business Management")
                gui.caption(
                    "Access your WhatsApp account on Meta to approve message templates, etc."
                )
            with col2:
                gui.anchor(
                    "Business Settings",
                    str(
                        furl(
                            "https://business.facebook.com/settings/whatsapp-business-accounts/"
                        )
                        / bi.wa_business_waba_id
                    ),
                    new_tab=True,
                )
                gui.anchor(
                    "WhatsApp Manager",
                    str(
                        furl(
                            "https://business.facebook.com/wa/manage/home/",
                            query_params=dict(waba_id=bi.wa_business_waba_id),
                        )
                    ),
                    new_tab=True,
                )

        col1, col2 = gui.columns(2, style=dict(alignItems="center"))
        with col1:
            gui.write("###### Add Deployment")
            gui.caption(f"Add another connection for {current_pr.title}.")
        with col2:
            gui.anchor(
                f'<img align="left" width="24" height="24" src="{icons.integrations_img}"> &nbsp; Add Deployment',
                str(
                    furl(
                        copilot_app_url(
                            current_sr=current_sr,
                            current_pr=current_pr,
                            tab=RecipeTabs.integrations,
                        )
                    )
                    / "add/"
                ),
                unsafe_allow_html=True,
            )

        gui.write("---")
        gui.newline()
        general_integration_settings(
            user=user,
            workspace=workspace,
            bi=bi,
            has_test_link=bool(test_link),
        )
        gui.write("---")

        if bi.platform in [Platform.SLACK, Platform.WHATSAPP, Platform.TWILIO]:
            gui.newline()
            broadcast_input(bi)
            gui.write("---")

        col1, col2 = gui.columns(2, style=dict(alignItems="center"))
        with col1:
            gui.write("###### Disconnect")
            gui.caption(
                f"Disconnect {current_pr.title} from {Platform(bi.platform).label} {bi.get_display_name()}."
            )
        with col2:
            if gui.button(
                "💔️ Disconnect",
                key="btn_disconnect",
            ):
                if bi.platform == Platform.TELEGRAM:
                    bi.telegram_bot_token = ""
                    bi.telegram_bot_id = None
                    bi.telegram_bot_user_name = ""

                bi.saved_run = None
                bi.published_run = None
                bi.save()
                gui.rerun()
