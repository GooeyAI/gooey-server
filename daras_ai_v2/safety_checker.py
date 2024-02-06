from app_users.models import AppUser
from daras_ai_v2.azure_image_moderation import is_image_nsfw
from daras_ai_v2.functional import flatten
from daras_ai_v2 import settings
from recipes.CompareLLM import CompareLLMPage


def safety_checker(*, text: str | None = None, image: str | None = None):
    assert text or image, "safety_checker: at least one of text, image is required"

    if text:
        safety_checker_text(text)
    if image:
        safety_checker_image(image)


def safety_checker_text(text_input: str):
    # ge the billing account for the checker
    billing_account = AppUser.objects.get_or_create_from_email(
        settings.SAFTY_CHECKER_BILLING_EMAIL
    )[0]

    # run in a thread to avoid messing up threadlocals
    result, sr = (
        CompareLLMPage()
        .get_published_run(published_run_id=settings.SAFTY_CHECKER_EXAMPLE_ID)
        .saved_run.submit_api_call(
            current_user=billing_account,
            request_body=dict(variables=dict(input=text_input)),
        )
    )

    # wait for checker
    result.get(disable_sync_subtasks=False)
    sr.refresh_from_db()
    # if checker failed, raise error
    if sr.error_msg:
        raise RuntimeError(sr.error_msg)

    # check for flagged
    for text in flatten(sr.state["output_text"].values()):
        lines = text.strip().splitlines()
        if not lines:
            continue
        if lines[-1].upper().endswith("FLAGGED"):
            raise ValueError(
                "Your request was rejected as a result of our safety system. Your prompt may contain text that is not allowed by our safety system."
            )


def safety_checker_image(image_url: str, cache: bool = False) -> None:
    if is_image_nsfw(image_url=image_url, cache=cache):
        raise ValueError(
            "Your request was rejected as a result of our safety system. "
            "Your input image may contain contents that are not allowed "
            "by our safety system."
        )
