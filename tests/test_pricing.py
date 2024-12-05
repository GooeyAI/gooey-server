from starlette.testclient import TestClient

from bots.models import AppUser
from bots.models import SavedRun, Workflow
from daras_ai_v2.lipsync_api import LipsyncModel
from payments.models import Subscription
from payments.plans import PricingPlan
from recipes.CompareLLM import CompareLLMPage
from recipes.Lipsync import LipsyncPage
from recipes.VideoBots import VideoBotsPage
from server import app
from usage_costs.models import UsageCost, ModelPricing

client = TestClient(app)


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
    copilot_page = VideoBotsPage(
        user=user,
        query_params=dict(run_id=bot_saved_run.run_id or "", uid=user.uid or ""),
    )
    assert (
        copilot_page.get_price_roundoff(state=state)
        == 210 + copilot_page.PROFIT_CREDITS
    )


def test_multiple_llm_sums_usage_cost(transactional_db):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.COMPARE_LLM,
        run_id="test_run",
        uid=user.uid,
    )

    state = {
        "tts_provider": "google",
        "num_outputs": 3,
        "selected_models": ["test_model1", "test_model2"],
    }

    model_pricing1 = ModelPricing.objects.create(
        model_id=1,
        sku=1,
        unit_cost=2.1,
        unit_quantity=1,
        category=1,
        provider=1,
        model_name="test_model1",
    )
    model_pricing2 = ModelPricing.objects.create(
        model_id=2,
        sku=1,
        unit_cost=1,
        unit_quantity=1,
        category=1,
        provider=1,
        model_name="test_model2",
    )

    UsageCost.objects.create(
        saved_run=bot_saved_run,
        pricing=model_pricing1,
        quantity=1,
        unit_cost=model_pricing1.unit_cost,
        unit_quantity=model_pricing1.unit_quantity,
        dollar_amount=model_pricing1.unit_cost * 1 / model_pricing1.unit_quantity,
    )
    UsageCost.objects.create(
        saved_run=bot_saved_run,
        pricing=model_pricing2,
        quantity=1,
        unit_cost=model_pricing2.unit_cost,
        unit_quantity=model_pricing2.unit_quantity,
        dollar_amount=model_pricing2.unit_cost * 1 / model_pricing2.unit_quantity,
    )

    llm_page = CompareLLMPage(
        user=user,
        query_params=dict(run_id=bot_saved_run.run_id or "", uid=user.uid or ""),
    )
    assert llm_page.get_price_roundoff(state=state) == (310 + llm_page.PROFIT_CREDITS)


def test_workflowmetadata_2x_multiplier(transactional_db):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.COMPARE_LLM,
        run_id="test_run",
        uid=user.uid,
    )

    state = {
        "tts_provider": "google",
        "num_outputs": 1,
        "selected_models": ["test_model"],
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

    metadata = Workflow.COMPARE_LLM.get_or_create_metadata()
    metadata.price_multiplier = 2
    metadata.save()

    llm_page = CompareLLMPage(
        user=user,
        query_params=dict(run_id=bot_saved_run.run_id or "", uid=user.uid or ""),
    )
    assert (
        llm_page.get_price_roundoff(state=state) == (210 + llm_page.PROFIT_CREDITS) * 2
    )


def test_lipsync_pricing(transactional_db):
    page = LipsyncPage(user=AppUser.objects.create(is_anonymous=False, balance=5))
    assert (
        page.get_price_roundoff(
            state=dict(selected_model=LipsyncModel.Wav2Lip.name, duration_sec=32)
        )
        == 42
    )
    assert (
        page.get_price_roundoff(
            state=dict(selected_model=LipsyncModel.SadTalker.name, duration_sec=32)
        )
        == 84
    )

    page.current_workspace.subscription = Subscription.objects.create(
        plan=PricingPlan.ENTERPRISE.db_value
    )
    assert (
        page.get_price_roundoff(
            state=dict(selected_model=LipsyncModel.Wav2Lip.name, duration_sec=32)
        )
        == 66
    )
    assert (
        page.get_price_roundoff(
            state=dict(selected_model=LipsyncModel.SadTalker.name, duration_sec=32)
        )
        == 132
    )
