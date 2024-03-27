from bots.models import AppUser
from recipes.VideoBots import VideoBotsPage
from usage_costs.models import UsageCost, ModelPricing
from bots.models import SavedRun, Workflow


def test_copilot_get_raw_price_round_up(transactional_db):
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    state = {
        "tts_provider": "google",
        "num_outputs": 1,
    }
    bot_saved_run = SavedRun.objects.create(
        workflow=Workflow.VIDEO_BOTS,
        run_id="test_run",
        uid=user.uid,
    )

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

    video_bot_page = VideoBotsPage(run_user=user, request=dict())
    assert video_bot_page.get_raw_price(state=state) == 6
