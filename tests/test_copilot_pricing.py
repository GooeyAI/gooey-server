import pytest
import math
from starlette.requests import Request
from bots.models import AppUser
from recipes.VideoBots import VideoBotsPage
from usage_costs.models import UsageCost, ModelPricing
from bots.models import SavedRun, Workflow
from gooey_ui.state import set_query_params
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
def test_get_raw_price(transactional_db, mock_gui_runner, force_authentication):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="test_run",
        uid=user.uid,
    )

    state = {
        "input_prompt": "You are Farmer.CHAT - an intelligent AI assistant built by Gooey.AI and DigitalGreen.org to help Indian farmers and agriculture agents. Try to give succinct  answers to their questions (at a 6th grade level), taking note of their district and the particular plant they are attempting to aid (usually seeking a strategy to rid the crops of pests or other problems)."
    }

    r = client.post(
        f"/v2/{VideoBotsPage.slug_versions[0]}/?run_id={bot_saved_run.run_id}&uid={user.uid}",
        json=VideoBotsPage.get_example_request_body(state),
        headers={"Authorization": f"Token None"},
        allow_redirects=False,
    )
    assert r.status_code == 200
    assert r.text

    res = r.json()

    usage_cost_dollar_amt = math.ceil(
        UsageCost.objects.filter(saved_run__run_id=res["run_id"]).aggregate(
            Sum("dollar_amount")
        )["dollar_amount__sum"]
    )

    assert usage_cost_dollar_amt == VideoBotsPage(run_user=user).get_raw_price(
        state=state
    )
