from contextlib import contextmanager

from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.azure_image_moderation import is_image_nsfw
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.functional import flatten
from recipes.CompareLLM import CompareLLMPage

SAFETY_CHECKER_MSG = "Your request was rejected as a result of our safety system. Your input may contain contents that are not allowed by our safety system."


def safety_checker(*, text: str | None = None, image: str | None = None):
    assert text or image, "safety_checker: at least one of text, image is required"

    if text:
        safety_checker_text(text)
    if image:
        safety_checker_image(image)


def safety_checker_text(text_input: str):
    # get the billing account for the checker
    billing_account = AppUser.objects.get_or_create_from_email(
        settings.SAFETY_CHECKER_BILLING_EMAIL
    )[0]
    workspace, _ = billing_account.get_or_create_personal_workspace()

    # run in a thread to avoid messing up threadlocals
    result, sr = (
        CompareLLMPage()
        .get_pr_from_example_id(example_id=settings.SAFETY_CHECKER_EXAMPLE_ID)
        .submit_api_call(
            workspace=workspace,
            current_user=billing_account,
            request_body=dict(variables=dict(input=text_input)),
            deduct_credits=False,
        )
    )

    # wait for checker
    sr.wait_for_celery_result(result)
    # if checker failed, raise error
    if sr.error_msg:
        raise RuntimeError(sr.error_msg)

    # check for flagged
    for text in flatten(sr.state["output_text"].values()):
        lines = text.strip().splitlines()
        if not lines:
            continue
        if lines[-1].upper().endswith("FLAGGED"):
            raise UserError(SAFETY_CHECKER_MSG)


def safety_checker_image(image_url: str, cache: bool = False) -> None:
    if is_image_nsfw(image_url=image_url, cache=cache):
        raise UserError(SAFETY_CHECKER_MSG)


@contextmanager
def capture_openai_content_policy_violation():
    import openai

    try:
        yield
    except openai.BadRequestError as e:
        if e.response.status_code == 400 and e.code in (
            "content_policy_violation",
            "content_filter",
        ):
            raise UserError(SAFETY_CHECKER_MSG) from e
        raise
