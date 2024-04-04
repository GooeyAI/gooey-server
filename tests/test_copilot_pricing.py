import pytest
import typing
from bots.models import AppUser
from recipes.VideoBots import VideoBotsPage
from usage_costs.models import UsageCost, ModelPricing
from bots.models import SavedRun, Workflow
from gooey_ui.state import set_query_params
from daras_ai_v2.base import BasePage
from starlette.testclient import TestClient
from server import app
from django.db.models import Sum

client = TestClient(app)


@pytest.mark.django_db
def test_copilot_get_raw_price_round_up(transactional_db):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="test_run",
        uid=user.uid,
    )

    state = {
        "tts_provider": "google",
        "num_outputs": 1,
    }

    model_pricing = ModelPricing.objects.create(
        model_id=1,
        sku=1,
        unit_cost=2.1,
        unit_quantity=1,
        category=1,
        provider=1,
        model_name="test_model",
    )

    UsageCost.objects.create(
        saved_run=bot_saved_run,
        pricing=model_pricing,
        quantity=1,
        unit_cost=model_pricing.unit_cost,
        unit_quantity=model_pricing.unit_quantity,
        dollar_amount=model_pricing.unit_cost * 1 / model_pricing.unit_quantity,
    )
    copilot_page = VideoBotsPage(run_user=user)
    set_query_params({"run_id": bot_saved_run.run_id or "", "uid": user.uid or ""})
    assert copilot_page.get_price_roundoff(state=state) == 6


@pytest.mark.django_db
def test_get_raw_price(
    transactional_db, mock_gui_runner, force_authentication, threadpool_subtest
):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="test_run",
        uid=user.uid,
    )
    copilot_page = VideoBotsPage(run_user=user)
    set_query_params({"run_id": bot_saved_run.run_id or "", "uid": user.uid or ""})
    _test_get_raw_price(copilot_page, bot_saved_run)


def _test_get_raw_price(copilot_page, bot_saved_run):
    state = {
        "tts_provider": "google",
        "num_outputs": 1,
    }
    r = client.post(
        f"/v2/{copilot_page.slug_versions[0]}/",
        params={"run_id": "test_run", "uid": "test_user"},
        json=copilot_page.get_example_request_body(state),
        headers={"Authorization": f"Token None"},
        allow_redirects=False,
    )
    usage_cost_dollar_amt = UsageCost.objects.filter(saved_run=bot_saved_run).aggregate(
        Sum("dollar_amount")
    )["dollar_amount__sum"]
    assert usage_cost_dollar_amt == copilot_page.get_raw_price(state=state)
