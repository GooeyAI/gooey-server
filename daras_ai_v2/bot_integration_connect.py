import json

from fastapi import HTTPException, Request

from bots.models import (
    BotIntegration,
    Platform,
    PublishedRun,
    WorkflowAccessLevel,
)
from daras_ai_v2 import settings
import secrets

import requests
from django.db import IntegrityError

from app_users.models import AppUser
from daras_ai_v2.exceptions import UserError
from workspaces.models import Workspace


def create_deployment(
    *,
    platform: Platform,
    workspace: Workspace,
    user: AppUser,
    published_run: PublishedRun,
    country_code: str | None,
    telegram_bot_token: str | None,
) -> tuple[BotIntegration | None, str]:
    from number_cycling.models import SharedPhoneNumber
    from routers.facebook_api import fb_connect_url, wa_connect_url
    from routers.slack_api import slack_connect_url

    if platform == Platform.TELEGRAM:
        if not telegram_bot_token:
            raise UserError("Please provide a Telegram bot token.")
        telegram_bot_id, telegram_bot_username = init_telegram_deployment(
            telegram_bot_token
        )
    else:
        telegram_bot_id = telegram_bot_username = None

    if not WorkflowAccessLevel.can_user_edit_published_run(
        workspace=workspace,
        user=user,
        pr=published_run,
    ):
        first_name_possesive = user.first_name_possesive() or "My"
        title = f"{first_name_possesive} {published_run.title}"
        published_run = published_run.duplicate(
            user=user,
            workspace=workspace,
            title=title,
            notes=published_run.notes,
        )

    match platform:
        case Platform.TELEGRAM:
            bi = BotIntegration.objects.create(
                name=published_run.title,
                created_by=user,
                workspace=workspace,
                platform=platform,
                telegram_bot_token=telegram_bot_token,
                telegram_bot_id=telegram_bot_id,
                telegram_bot_user_name=telegram_bot_username,
            )
        case Platform.WEB:
            bi = BotIntegration.objects.create(
                name=published_run.title,
                created_by=user,
                workspace=workspace,
                platform=Platform.WEB,
            )
        case Platform.WHATSAPP:
            try:
                bi = create_shared_phone_number_deployment(
                    name=published_run.title,
                    created_by=user,
                    workspace=workspace,
                    platform=Platform.WHATSAPP,
                    country_code=country_code,
                )
            except SharedPhoneNumber.DoesNotExist:
                return None, wa_connect_url(published_run.id)
        case Platform.TWILIO:
            try:
                bi = create_shared_phone_number_deployment(
                    name=published_run.title,
                    created_by=user,
                    workspace=workspace,
                    platform=Platform.TWILIO,
                    country_code=country_code,
                )
            except SharedPhoneNumber.DoesNotExist as e:
                raise UserError(str(e)) from e
        case Platform.SLACK:
            return None, slack_connect_url(published_run.id)
        case Platform.FACEBOOK:
            return None, fb_connect_url(published_run.id)
        case _:
            raise ValueError(f"Unsupported platform: {platform}")

    return bi, connect_bot_to_published_run(bi, published_run, overwrite=True)


def create_shared_phone_number_deployment(
    name: str,
    created_by,
    workspace: Workspace,
    platform: Platform,
    country_code: str | None,
) -> BotIntegration:
    from number_cycling.models import SharedPhoneNumber

    if platform != Platform.TWILIO and platform != Platform.WHATSAPP:
        raise ValueError("Invalid platform")

    shared_phone_number = SharedPhoneNumber.objects.any_active_number(
        platform, country_code=country_code
    )
    for _ in range(10):
        try:
            return BotIntegration.objects.create(
                name=name,
                created_by=created_by,
                workspace=workspace,
                platform=platform.value,
                wa_phone_number_id=shared_phone_number.wa_phone_number_id,
                wa_phone_number=shared_phone_number.wa_phone_number,
                twilio_phone_number=shared_phone_number.twilio_phone_number,
                twilio_phone_number_sid=shared_phone_number.twilio_phone_number_sid,
                shared_phone_number=shared_phone_number,
                extension_number=10_000 + secrets.randbelow(90_000),
            )
        except IntegrityError:
            continue
    raise RuntimeError("Unable to create unique 5-digit extension number")


def init_telegram_deployment(bot_token: str) -> tuple[str, str]:
    from daras_ai_v2.fastapi_tricks import get_api_route_url
    from daras_ai_v2.telegram_bot import (
        get_telegram_bot_info,
        set_telegram_commands,
        set_telegram_webhook,
    )
    from routers.telegram_api import telegram_webhook

    try:
        bot_info = get_telegram_bot_info(bot_token)
    except requests.exceptions.HTTPError as e:
        raise UserError(f"Invalid bot token: {e}") from e

    bot_id = str(bot_info["id"])
    bot_username = bot_info.get("username", "")

    if BotIntegration.objects.filter(telegram_bot_id=bot_id).exists():
        raise UserError(
            "This Telegram bot is already connected to a Gooey.AI workflow. "
            "Please disconnect it first or use a different bot.",
        )

    webhook_url = get_api_route_url(
        telegram_webhook,
        path_params=dict(bot_id=bot_id),
    )
    try:
        set_telegram_webhook(
            bot_token,
            webhook_url,
            secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
        )
    except requests.exceptions.HTTPError as e:
        raise UserError(f"Failed to set webhook: {e}") from e

    try:
        set_telegram_commands(bot_token)
    except requests.exceptions.HTTPError as e:
        raise UserError(f"Failed to register Telegram commands: {e}") from e
    return bot_id, bot_username


def connect_bot_to_published_run(
    bi: BotIntegration, published_run: PublishedRun | None, *, overwrite: bool
) -> str:
    """
    Connect the bot integration to the provided saved and published runs.
    Returns the redirect url to the integrations page for that bot integration.
    """

    from daras_ai_v2.slack_bot import send_confirmation_msg

    if not bi.published_run or overwrite:
        bi.published_run = published_run
        bi.save(update_fields=["published_run"])
        if bi.platform == Platform.SLACK:
            send_confirmation_msg(bi)

    return bi.get_deployment_url()


def load_published_run_from_state(request: Request) -> PublishedRun:
    pr_id = json.loads(request.query_params.get("state") or "{}").get("pr_id")
    try:
        return PublishedRun.objects.get(id=pr_id)
    except PublishedRun.DoesNotExist:
        raise HTTPException(status_code=404, detail="Published Run not found")
