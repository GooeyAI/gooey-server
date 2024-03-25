from bots.models import AppUser
from recipes.VideoBots import VideoBotsPage
from usage_costs.models import UsageCost
from bots.models import SavedRun


def test_copilot_get_raw_price_round_up():
    user = AppUser.objects.create(
        uid="test_user", is_paying=False, balance=1000, is_anonymous=False
    )
    state = {
        "tts_provider": "google",
        "num_outputs": 1,
    }
    bot_saved_run = SavedRun.objects.create(
        parent_version=None,
        workflow="Copilot",
        run_id="test_run",
        uid=user.uid,
    )
    bot_usage_cost = UsageCost.objects.create(
        saved_run=bot_saved_run,
        dollar_amount=2.1,
    )
    assert VideoBotsPage.get_raw_price(self=VideoBotsPage(), state=state) == 6
