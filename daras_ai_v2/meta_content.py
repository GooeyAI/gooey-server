from firebase_admin import auth
from firebase_admin.auth import UserNotFoundError

from daras_ai.image_input import truncate_text_words
from daras_ai_v2.base import BasePage


def meta_title_for_page(
    *,
    page: BasePage,
    state: dict,
    run_id: str,
    uid: str,
    example_id: str,
) -> str:
    parts = []

    prompt = truncate_text_words(page.preview_input(state) or "", maxlen=100)
    end_suffix = f"{page.title} on Gooey.AI"

    if run_id and uid:
        parts.append(prompt)
        try:
            user = auth.get_user(uid)
        except UserNotFoundError:
            user = None
        if user and user.display_name:
            parts.append(user_name_possesive(user.display_name) + " " + end_suffix)
        else:
            parts.append(end_suffix)
    elif example_id:
        parts.append(prompt)
        parts.append(end_suffix)
    else:
        parts.append(page.title)
        parts.append("AI API, workflow & prompt shared on Gooey.AI")

    return " • ".join(p for p in parts if p)


def user_name_possesive(name: str) -> str:
    if name.endswith("s"):
        return name + "'"
    else:
        return name + "'s"


def meta_description_for_page(
    *,
    page: BasePage,
    state: dict,
    run_id: str,
    uid: str,
    example_id: str,
) -> str:
    description = page.preview_description(state)

    # updated_at = state.get("updated_at")
    # if updated_at:
    #     description = updated_at.strftime("%d-%b-%Y") + " — " + description

    if (run_id and uid) or example_id or not description:
        description += " AI API, workflow & prompt shared on Gooey.AI."

    return description
