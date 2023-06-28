from firebase_admin import auth

from app_users.models import AppUser
from daras_ai.image_input import truncate_text_words
from daras_ai_v2.base import BasePage
from daras_ai_v2.meta_preview_url import meta_preview_url


def build_meta_tags(
    *,
    url: str,
    page: BasePage,
    state: dict,
    run_id: str,
    uid: str,
    example_id: str,
) -> list[dict]:
    title = meta_title_for_page(
        page=page,
        state=state,
        run_id=run_id,
        uid=uid,
        example_id=example_id,
    )
    description = meta_description_for_page(
        page=page,
        state=state,
        run_id=run_id,
        uid=uid,
        example_id=example_id,
    )
    image = meta_preview_url(page.preview_image(state), page.fallback_preivew_image())

    ret = [
        dict(title=title),
        dict(name="title", content=title),
        dict(property="og:type", content="website"),
        dict(property="og:url", content=url),
        dict(property="og:title", content=title),
        dict(property="twitter:card", content="summary_large_image"),
        dict(property="twitter:url", content=url),
        dict(property="twitter:title", content=title),
    ]
    if description:
        ret += [
            dict(name="description", content=description),
            dict(property="og:description", content=description),
            dict(property="twitter:description", content=description),
        ]
    if image:
        ret += [
            dict(name="image", content=image),
            dict(property="og:image", content=image),
            dict(property="twitter:image", content=image),
        ]
    return ret


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
    title = state.get("__title") or page.title
    end_suffix = f"{title} on Gooey.AI"

    if run_id and uid:
        parts.append(prompt)
        try:
            user = AppUser.objects.get_or_create_from_uid(uid)[0]
        except auth.UserNotFoundError:
            user = None
        if user and user.display_name:
            parts.append(user_name_possesive(user.display_name) + " " + end_suffix)
        else:
            parts.append(end_suffix)
    elif example_id:
        # DO NOT SHOW PROMPT FOR EXAMPLES
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
    description = state.get("__notes") or page.preview_description(state)
    # updated_at = state.get("updated_at")
    # if updated_at:
    #     description = updated_at.strftime("%d-%b-%Y") + " — " + description

    if (run_id and uid) or example_id or not description:
        description += " AI API, workflow & prompt shared on Gooey.AI."

    return description
