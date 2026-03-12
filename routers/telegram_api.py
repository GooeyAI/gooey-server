from starlette.background import BackgroundTasks
from starlette.requests import Request
from starlette.responses import Response

from daras_ai_v2 import settings
from daras_ai_v2.bots import BotIntegrationLookupFailed, msg_handler
from daras_ai_v2.fastapi_tricks import fastapi_request_json
from daras_ai_v2.telegram_bot import TelegramBot
from routers.custom_api_router import CustomAPIRouter

router = CustomAPIRouter()


@router.post("/__/telegram/webhook/{bot_id}/")
def telegram_webhook(
    request: Request,
    bot_id: str,
    background_tasks: BackgroundTasks,
    data: dict = fastapi_request_json,
):
    if settings.TELEGRAM_WEBHOOK_SECRET:
        secret = request.headers.get("x-telegram-bot-api-secret-token") or ""
        if secret != settings.TELEGRAM_WEBHOOK_SECRET:
            return Response(status_code=403)

    print(f"{bot_id=} {data=}")
    try:
        bot = TelegramBot(bot_id=bot_id, data=data)
    except (BotIntegrationLookupFailed, ValueError):
        return Response(status_code=200)

    background_tasks.add_task(msg_handler, bot)

    return Response(status_code=200)
