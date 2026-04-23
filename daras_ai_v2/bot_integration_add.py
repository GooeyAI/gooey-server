from __future__ import annotations

import typing

import gooey_gui as gui
from django.utils.text import slugify

from app_users.models import AppUser
from bots.models import Platform, PublishedRun, SavedRun, WorkflowAccessLevel
from daras_ai_v2 import icons
from daras_ai_v2.base import RecipeTabs
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.exceptions import UserError
from workspaces.models import Workspace


class DeployChoice(typing.NamedTuple):
    platform: Platform
    img: str
    label: str


deploy_choices = [
    DeployChoice(
        platform=Platform.WEB,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/29c0ffa8-29d8-11f1-ae3c-02420a00014a/image_400x400.png",
        label="Connect to your own App or Website.",
    ),
    DeployChoice(
        platform=Platform.WHATSAPP,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/1e49ad50-d6c9-11ee-99c3-02420a000123/thumbs/Digital_Inline_Green_400x400.png",
        label="Instantly connect WhatsApp via a test number, connect your own or buy a number on us. [Help Guide](https://docs.gooey.ai/ai-agent/how-to-deploy-an-ai-copilot/deploy-on-whatsapp)",
    ),
    DeployChoice(
        platform=Platform.TWILIO,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b0830a1e-0b8c-11f1-a876-02420a000176/Adobe%20Express%20-%20file.png",
        label="Call or text your copilot with a free test number (or buy one). [Help Guide](https://docs.gooey.ai/ai-agent/how-to-deploy-an-ai-copilot/deploy-to-voice)",
    ),
    DeployChoice(
        platform=Platform.SLACK,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ee8c5b1c-d6c8-11ee-b278-02420a000126/thumbs/image_400x400.png",
        label="Connect to a Slack Channel. [Help Guide](https://gooey.ai/docs/guides/copilot/deploy-to-slack)",
    ),
    DeployChoice(
        platform=Platform.FACEBOOK,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/9f201a92-1e9d-11ef-884b-02420a000134/thumbs/image_400x400.png",
        label="Connect to a Facebook Page you own. [Help Guide](https://gooey.ai/docs/guides/copilot/deploy-to-facebook)",
    ),
    DeployChoice(
        platform=Platform.TELEGRAM,
        img="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/40df4ffa-29d8-11f1-94de-02420a00014b/telegram_logo.png",
        label="Connect to Telegram.",
    ),
]


def render_integrations_add(
    *,
    label: str,
    current_sr: SavedRun,
    pr: PublishedRun,
    user: AppUser,
    workspace: Workspace,
) -> None:
    gui.write(label, unsafe_allow_html=True, className="text-center")

    gui.newline()

    pressed_platform = None
    with (
        gui.tag("table", className="d-flex justify-content-center"),
        gui.tag("tbody"),
    ):
        for choice in deploy_choices:
            with gui.tag("tr"):
                with gui.tag("td"):
                    if gui.button(
                        f'<img src="{choice.img}" alt="{choice.platform.name}" style="max-width: 80%; max-height: 90%" draggable="false">',
                        className="p-0 border border-1 border-secondary rounded",
                        style=dict(width="160px", height="60px"),
                    ):
                        pressed_platform = choice.platform
                with gui.tag("td", className="ps-3"):
                    gui.caption(choice.label)

    try:
        handle_bot_integration_add(
            platform=pressed_platform,
            current_sr=current_sr,
            pr=pr,
            user=user,
            workspace=workspace,
        )
    except UserError as e:
        gui.error(str(e))
        return

    if not WorkflowAccessLevel.can_user_edit_published_run(
        workspace=workspace,
        user=user,
        pr=pr,
    ):
        gui.caption(
            "P.S. You're not an owner of this saved workflow, so we'll create a copy of it in your Saved Runs.",
            className="text-center text-muted",
        )

    gui.newline()

    api_tab_url = copilot_app_url(
        current_sr=current_sr,
        current_pr=pr,
        tab=RecipeTabs.run_as_api,
    )
    gui.write(
        f"Or use [our API]({api_tab_url}) to build custom integrations with your server.",
        className="text-center",
    )


NUMBER_CYCLING_PLATFORMS = (Platform.TWILIO, Platform.WHATSAPP)


def handle_bot_integration_add(
    *,
    platform: Platform | None,
    current_sr: SavedRun,
    pr: PublishedRun,
    user: AppUser,
    workspace: Workspace,
) -> None:
    from celeryapp.tasks import send_integration_attempt_email
    from daras_ai_v2.bot_integration_connect import create_deployment

    dialog = gui.use_confirm_dialog(
        key="bot-integration-connect", close_on_confirm=False
    )
    platform_key = dialog.key + ":platform"

    if platform == Platform.TELEGRAM or (
        platform in NUMBER_CYCLING_PLATFORMS and has_available_country_codes(platform)
    ):
        gui.session_state[platform_key] = platform.value
        dialog.set_open(True)

    telegram_bot_token = None
    country_code = ""

    if dialog.is_open:
        platform = Platform(gui.session_state.get(platform_key))
        if platform == Platform.TELEGRAM:
            telegram_bot_token = render_telegram_connect_dialog(dialog, pr.title)
            if not (dialog.pressed_confirm and telegram_bot_token):
                platform = None
        elif platform in NUMBER_CYCLING_PLATFORMS:
            country_code = render_country_code_dialog(
                dialog,
                platform=platform,
                title=f"Deploy {pr.title}",
                description="Select a country to get a free test number for testing your copilot.",
            )
            if not dialog.pressed_confirm:
                platform = None

    if not platform:
        return

    redirect_url = create_deployment(
        platform=platform,
        workspace=workspace,
        user=user,
        published_run=pr,
        country_code=country_code,
        telegram_bot_token=telegram_bot_token,
    )[1]

    if not user.is_admin():
        send_integration_attempt_email.delay(
            user_id=user.id,
            platform=platform,
            run_url=copilot_app_url(current_sr=current_sr, current_pr=pr),
        )

    raise gui.RedirectException(redirect_url)


def has_available_country_codes(platform: Platform) -> bool:
    from number_cycling.models import SharedPhoneNumber

    return SharedPhoneNumber.objects.available_country_codes(platform).count() > 1


def render_telegram_connect_dialog(dialog: gui.ConfirmDialogRef, run_title: str) -> str:
    header, body, footer = gui.modal_scaffold()
    bot_name = run_title.strip() or "My Bot"
    bot_username = _suggested_telegram_bot_username(run_title)

    with header:
        gui.markdown("### Deploy to Telegram")

    with body:
        gui.markdown("**Step 1: Open BotFather**")
        gui.html(
            '<a class=" btn btn-theme btn-secondary w-100 mb-3" '
            'href="https://t.me/BotFather?text=/newbot" target="_blank">'
            f"{icons.telegram} Open BotFather"
            "</a>",
        )
        gui.markdown("**Step 2: Name your bot & add a username**")
        gui.markdown("Send: *`/newbot`* to BotFather to get started")
        _copiable_field("Suggested bot name", bot_name)
        _copiable_field("Suggested bot username", bot_username)

        gui.markdown("**Step 3: Paste in your bot's token**")
        bot_token = gui.text_input(
            "Bot token",
            key="telegram-bot-token",
            placeholder="e.g. 123456789:ABCdefGhIJKlmNoPQRsTUVwxYZ",
        )
        bot_token = (bot_token or "").strip()

    with footer:
        with gui.div(className="d-flex align-items-center gap-2 w-100"):
            with gui.div(className="me-auto"):
                gui.anchor(
                    href="https://docs.gooey.ai/telegram-help",
                    label="Need help?",
                    new_tab=True,
                    type="link",
                )
            gui.button(
                "Cancel",
                key=dialog.close_btn_key,
                type="tertiary",
            )
            gui.button(
                "Connect",
                key=dialog.confirm_btn_key,
                type="primary",
                disabled=not (bot_token or "").strip(),
            )

    return bot_token


def copilot_app_url(
    *,
    current_sr: SavedRun,
    current_pr: PublishedRun,
    tab: RecipeTabs = RecipeTabs.run,
    path_params: dict | None = None,
) -> str:
    from recipes.VideoBots import VideoBotsPage

    return VideoBotsPage.app_url(
        tab=tab,
        example_id=current_pr.published_run_id,
        run_id=current_sr.run_id,
        uid=current_sr.uid,
        path_params=path_params,
    )


def render_country_code_dialog(
    dialog: gui.ConfirmDialogRef,
    *,
    platform: Platform,
    title: str,
    description: str,
) -> str:
    from number_cycling.models import SharedPhoneNumber
    from number_cycling.utils import country_code_label

    country_codes = list(SharedPhoneNumber.objects.available_country_codes(platform))

    header, body, footer = gui.modal_scaffold()

    with header:
        gui.markdown(f"### {title}")

    with body:
        gui.markdown(description)
        with gui.div(className="pb-3"):
            selected_country_code = gui.selectbox(
                label="",
                options=country_codes,
                format_func=country_code_label,
                label_visibility="collapsed",
                key=f"{platform}-country-code-dialog",
            )

    with footer:
        gui.button("Cancel", key=dialog.close_btn_key, type="tertiary")
        gui.button(
            "Connect",
            key=dialog.confirm_btn_key,
            type="primary",
            disabled=not selected_country_code,
        )

    return selected_country_code or ""


def _copiable_field(label: str, value: str):
    with gui.div(className="mb-2"):
        gui.html(f"<small class='text-muted'>{label}</small>")
        with gui.div(className="d-flex align-items-center gap-2"):
            gui.markdown(value)
            copy_to_clipboard_button(
                label=icons.copy_solid,
                value=value,
                type="link",
            )


def _suggested_telegram_bot_username(run_title: str) -> str:
    slug = slugify(run_title).replace("-", " ")
    if not slug.strip():
        slug = "my bot"
    words = slug.split()
    camel = "".join(w.capitalize() for w in words)
    if camel.endswith("Bot") or camel.endswith("bot"):
        return camel
    return f"{camel}Bot"
