import json

from fastapi import HTTPException, Request

from bots.models import (
    BotIntegration,
    Platform,
    PublishedRun,
)
from daras_ai_v2.base import RecipeTabs


def connect_bot_to_published_run(
    bi: BotIntegration, published_run: PublishedRun | None
) -> str:
    """
    Connect the bot integration to the provided saved and published runs.
    Returns the redirect url to the integrations page for that bot integration.
    """

    from daras_ai_v2.slack_bot import send_confirmation_msg
    from recipes.VideoBots import VideoBotsPage

    print(f"Connecting {bi} to {published_run}")

    bi.published_run = published_run
    bi.save(update_fields=["published_run"])

    if bi.platform == Platform.SLACK:
        send_confirmation_msg(bi)

    return VideoBotsPage.app_url(
        tab=RecipeTabs.integrations,
        example_id=published_run.published_run_id,
        path_params=dict(integration_id=bi.api_integration_id()),
    )


def load_published_run_from_state(request: Request) -> PublishedRun:
    pr_id = json.loads(request.query_params.get("state") or "{}").get("pr_id")
    try:
        return PublishedRun.objects.get(id=pr_id)
    except PublishedRun.DoesNotExist:
        raise HTTPException(status_code=404, detail="Published Run not found")
