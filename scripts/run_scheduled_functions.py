from django.utils import timezone
import sentry_sdk
from bots.models import BotIntegrationScheduledFunction
from daras_ai.image_input import upload_file_from_bytes
from recipes.VideoBotsStats import get_conversations_and_messages, get_tabular_data


def run():
    for sf in BotIntegrationScheduledFunction.objects.select_related(
        "bot_integration"
    ).all():
        print(sf)
        bi = sf.bot_integration
        today = timezone.now().date()
        conversations, messages = get_conversations_and_messages(bi)
        df = get_tabular_data(
            bi=sf.bot_integration,
            conversations=conversations,
            messages=messages,
            details="Messages",
            sort_by=None,
            start_date=today,
            end_date=today,
        )
        csv = df.to_csv()
        csv_url = upload_file_from_bytes(
            filename=f"stats-{today.strftime('%Y-%m-%d')}.csv",
            data=csv,
            content_type="text/csv",
        )

        fn_sr, fn_pr = sf.get_runs()
        result, fn_sr = fn_sr.submit_api_call(
            workspace=bi.workspace,
            request_body=dict(variables={"message_history_csv_url": csv_url}),
            parent_pr=fn_pr,
            current_user=bi.workspace.created_by,
        )
        fn_sr.wait_for_celery_result(result)
        # if failed, raise error
        if fn_sr.error_msg:
            print("errored... {fn_sr.error_msg}")
            sentry_sdk.capture_exception(RuntimeError(fn_sr.error_msg))
        else:
            print(f"completed... {fn_sr.get_app_url()}")
