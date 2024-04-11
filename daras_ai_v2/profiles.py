import hashlib
from html import escape as escape_html
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.db import IntegrityError, transaction
from fastapi import Request
from furl import furl

import gooey_ui as st
from app_users.models import AppUser
from bots.models import (
    PublishedRun,
    PublishedRunVersion,
    PublishedRunVisibility,
    SavedRun,
    Workflow,
)
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import icons, settings, urls
from daras_ai_v2.base import format_number_with_suffix
from daras_ai_v2.copy_to_clipboard_button_widget import copy_to_clipboard_button
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.meta_content import (
    SEP as META_SEP,
    TITLE_SUFFIX as META_TITLE_SUFFIX,
    raw_build_meta_tags,
)
from gooey_ui.components.pills import pill
from handles.models import Handle


@dataclass
class ContributionsSummary:
    total: int
    top_contributions: dict[Workflow, int]  # sorted dict


@dataclass
class PublicRunsSummary:
    total: int
    top_workflows: dict[Workflow, int]


def get_meta_tags_for_profile(user: AppUser):
    assert user.handle
    return raw_build_meta_tags(
        url=user.handle.get_app_url(),
        title=_get_meta_title_for_profile(user),
        description=_get_meta_description_for_profile(user) or None,
        image=get_profile_image(user),
        canonical_url=user.handle.get_app_url(),
    )


def user_profile_page(request: Request, user: AppUser):
    with st.div(className="mt-3"):
        user_profile_header(request, user)
    st.html("\n<hr>\n")
    user_profile_main_content(user)


def user_profile_header(request, user: AppUser):
    if user.banner_url:
        with _banner_image_div(user.banner_url, className="my-3"):
            pass

    with st.div(className="mt-3"):
        col1, col2 = st.columns([2, 10])

    with (
        col1,
        st.div(className="d-flex justify-content-center align-items-center h-100"),
    ):
        render_profile_image(
            get_profile_image(user),
            className="mb-3",
        )

    run_count = get_run_count(user)
    contribs = get_contributions_summary(user)

    with (
        col2,
        st.div(
            className="d-flex text-center flex-column justify-content-center align-items-center align-items-lg-start"
        ),
    ):
        with st.div(
            className="d-inline d-lg-flex w-100 justify-content-between align-items-end"
        ):
            with st.tag("h1", className="d-inline my-0 me-2"):
                st.html(escape_html(get_profile_title(user)))

            if request.user == user:
                with st.link(
                    to=urls.remove_hostname(
                        request.url_for("account", tab_path="profile")
                    ),
                    className="text-decoration-none btn btn-theme btn-secondary mb-0",
                ):
                    st.html(f"{icons.edit} Edit Profile")

        with st.tag("p", className="lead text-secondary mb-0"):
            st.html(escape_html(user.handle and user.handle.name or ""))

        if user.bio:
            with st.div(className="mt-2 text-secondary"):
                st.html(escape_html(user.bio))

        with st.div(className="mt-3 d-flex flex-column d-lg-block"):
            if user.github_username:
                with st.link(
                    to=github_url_for_username(user.github_username),
                    className="text-decoration-none",
                ):
                    pill(
                        f"{icons.github} " + escape_html(user.github_username),
                        unsafe_allow_html=True,
                        type=None,
                        className="text-black border border-dark fs-6 me-2 me-lg-4 mb-1",
                    )

            if user.website_url:
                with (
                    st.tag(
                        "span",
                        className="text-sm mb-1 me-2 me-lg-4 d-inline-block mb-1",
                    ),
                    st.link(to=user.website_url, className="text-decoration-none"),
                ):
                    st.html(
                        f"{icons.link} "
                        + escape_html(urls.remove_scheme(user.website_url))
                    )

            if user.company:
                with st.tag(
                    "span",
                    className="text-sm text-muted me-lg-4 mb-1 d-inline-block",
                ):
                    st.html(f"{icons.company} " + escape_html(user.company))

        top_contributions_text = make_natural_english_list(
            [
                f"{escape_html(workflow.short_title)} ({count})"
                for workflow, count in contribs.top_contributions.items()
            ],
            last_sep=", ",
        )

        st.html(
            f"""\
<div class="d-flex mt-3">
    <div class="me-3 text-secondary">
        {icons.run} {escape_html(format_number_with_suffix(run_count))} runs
    </div>
 
    <div class="text-start">
        <div>{contribs.total} contributions since {user.created_at.strftime("%b %Y")}</div>
        <small class="mt-1">
            {top_contributions_text}
        </small>
    </div>
</div>
"""
        )


def user_profile_main_content(user: AppUser):
    public_runs = PublishedRun.objects.filter(
        created_by=user,
        visibility=PublishedRunVisibility.PUBLIC,
    ).order_by("-updated_at")

    def _render(pr: PublishedRun):
        workflow = Workflow(pr.workflow)
        page_cls = workflow.page_cls

        pill(workflow.short_title, className="mb-2 border border-dark")
        page_cls().render_published_run_preview(pr)

    if public_runs:
        grid_layout(3, public_runs, _render)
    else:
        st.write("No public runs yet", className="text-muted")


def get_run_count(user: AppUser) -> int:
    return SavedRun.objects.filter(uid=user.uid).count()


def get_contributions_summary(user: AppUser, *, top_n: int = 3) -> ContributionsSummary:
    count_by_workflow = (
        PublishedRunVersion.objects.filter(changed_by=user)
        .values("published_run__workflow")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    total = sum(row["count"] for row in count_by_workflow)
    top_contributions = {
        Workflow(row["published_run__workflow"]): row["count"]
        for row in count_by_workflow[:top_n]
    }

    return ContributionsSummary(total=total, top_contributions=top_contributions)


def get_public_runs_summary(user: AppUser, *, top_n: int = 3) -> PublicRunsSummary:
    count_by_workflow = (
        user.published_runs.filter(visibility=PublishedRunVisibility.PUBLIC)
        .values("workflow")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    total = sum(row["count"] for row in count_by_workflow)
    top_workflows = {
        Workflow(row["workflow"]): row["count"] for row in count_by_workflow[:top_n]
    }

    return PublicRunsSummary(total=total, top_workflows=top_workflows)


def render_profile_image(url: str, **props):
    style = {
        "maxWidth": "200px",
        "aspectRatio": "1",
        "objectFit": "cover",
    } | props.pop("style", {})
    className = "w-100 rounded-circle " + props.pop("className", "")
    st.image(
        url,
        style=style,
        className=className,
        **props,
    )


def _set_new_profile_photo(user: AppUser, image_url: str):
    user.photo_url = image_url
    try:
        user.full_clean()
    except (ValidationError, IntegrityError) as e:
        st.error(e)
    else:
        user.save(update_fields=["photo_url"])


def _is_uploading_photo() -> bool:
    return bool(st.session_state.get("_uploading_photo"))


def _set_is_uploading_photo(val: bool):
    st.session_state["_uploading_photo"] = val


def edit_user_profile_page(user: AppUser):
    _edit_user_profile_header(user)
    _edit_user_profile_banner(user)

    colspec = [2, 10] if not _is_uploading_photo() else [6, 6]
    photo_col, form_col = st.columns(colspec)
    with photo_col:
        _edit_user_profile_photo_section(user)
    with form_col:
        _edit_user_profile_form_section(user)


def _edit_user_profile_header(user: AppUser):
    with st.div(
        className="d-block d-md-flex flex-row-reverse justify-content-between align-items-center"
    ):
        with st.tag(
            "a", href="/logout/", className="btn btn-theme btn-secondary d-inline-block"
        ):
            st.write("Sign out")
        st.write("# Update your Profile")

    with st.div(className="mb-3"):
        with st.tag("span"):
            with st.tag("span", className="text-muted"):
                st.html("Your profile and public saved runs appear on ")
            with st.tag("span"):
                st.html(
                    str(furl(settings.APP_BASE_URL) / "/")
                    + f"<strong>{escape_html(user.handle.name) if user.handle else 'your-username'}</strong> ",
                )

        if user.handle:
            copy_to_clipboard_button(
                f"{icons.copy} Copy",
                value=user.handle.get_app_url(),
                type="tertiary",
                className="m-0",
            )
            with st.link(
                to=user.handle.get_app_url(),
                className="btn btn-theme btn-tertiary m-0",
            ):
                st.html(f"{icons.preview} Preview")


def _banner_image_div(url: str | None, **props):
    style = {
        "minHeight": "200px",
        "maxHeight": "400px",
        "width": "100%",
        "aspectRatio": "3 / 1",
        "backgroundColor": "rgba(180, 180, 180, 1.0)",
    }
    if url:
        style |= {
            "backgroundImage": f'url("{url}")',
            "backgroundSize": "cover",
            "backgroundPosition": "center",
            "backgroundRepeat": "no-repeat",
        }

    className = "w-100 h-100 rounded-2 " + props.pop("className", "")
    style |= props.pop("style", {})
    return st.div(style=style, className=className)


def _edit_user_profile_banner(user: AppUser):
    def _is_uploading_banner_photo() -> bool:
        return bool(st.session_state.get("_uploading_banner_photo"))

    def _set_uploading_banner_photo(val: bool):
        if val:
            st.session_state["_uploading_banner_photo"] = val
        else:
            st.session_state.pop("_uploading_banner_photo", None)
            st.session_state.pop("banner_photo_url", None)

    def _get_uploading_banner_photo() -> str | None:
        return st.session_state.get("banner_photo_url")

    banner_photo = _get_uploading_banner_photo() or user.banner_url or None
    with _banner_image_div(
        banner_photo,
        className="d-flex justify-content-center align-items-center position-relative mb-3",
    ):
        if _is_uploading_banner_photo():
            translucent_style = {"backgroundColor": "rgba(255, 255, 255, 0.2)"}
            with (
                st.div(
                    className="d-flex justify-content-center align-items-center w-100 h-100",
                    style=translucent_style,
                ),
                st.div(),
            ):
                banner_url = st.file_uploader(
                    "", accept=["image/*"], key="banner_photo_url"
                )

                with st.div(className="d-flex justify-content-center"):
                    if banner_url and st.button(f"{icons.save} Save", type="primary"):
                        user.banner_url = banner_url
                        user.save(update_fields=["banner_url"])
                        _set_uploading_banner_photo(False)
                        st.experimental_rerun()

                    if st.button(
                        f"{icons.cancel} Cancel",
                        className="text-danger",
                    ):
                        _set_uploading_banner_photo(False)
                        st.experimental_rerun()
        else:
            with st.div(className="position-absolute bottom-0 end-0"):
                if user.banner_url and st.button(
                    f"{icons.clear} Clear",
                    type="tertiary",
                    className="text-dark",
                ):
                    user.banner_url = ""
                    user.save(update_fields=["banner_url"])
                    _set_uploading_banner_photo(False)
                    st.experimental_rerun()

                upload_banner_text = (
                    f"{icons.camera} Edit Cover Photo"
                    if user.banner_url
                    else f"{icons.camera} Add Cover Photo"
                )
                if st.button(
                    upload_banner_text, className="mb-3 me-3", type="secondary"
                ):
                    _set_uploading_banner_photo(True)
                    st.experimental_rerun()


def _edit_user_profile_photo_section(user: AppUser):
    with st.div(className="w-100 h-100 d-flex align-items-center flex-column"):
        if _is_uploading_photo():
            image_div = st.div(
                className="d-flex justify-content-center align-items-center"
            )
            image_url = st.file_uploader("", accept=["image/*"])

            with st.div(className="d-flex justify-content-center"):
                if st.button(
                    "Save", type="primary", disabled=not image_url, className="me-3"
                ):
                    _set_new_profile_photo(user, image_url)
                    _set_is_uploading_photo(False)
                    st.experimental_rerun()

                if st.button(
                    f"{icons.cancel} Cancel",
                    className="text-danger",
                ):
                    _set_is_uploading_photo(False)
                    st.experimental_rerun()

            with image_div:
                render_profile_image(get_profile_image(user))
        else:
            render_profile_image(get_profile_image(user))

            with st.div(className="mt-2"):
                if st.button(
                    f"{icons.camera} Upload",
                    type="link",
                    className="d-block text-decoration-none px-2 py-1 my-2",
                ):
                    _set_is_uploading_photo(True)
                    st.experimental_rerun()
                if user.photo_url and st.button(
                    f"{icons.clear} Clear",
                    type="link",
                    className="d-block text-decoration-none px-2 py-1 my-2",
                ):
                    _set_new_profile_photo(user, "")
                    st.experimental_rerun()


def _edit_user_profile_form_section(user: AppUser):
    user.display_name = st.text_input("Name", value=user.display_name)

    handle_style: dict[str, str] = {}
    if handle := st.text_input(
        "Username",
        value=(user.handle and user.handle.name or ""),
        style=handle_style,
    ):
        if not user.handle or user.handle.name != handle:
            try:
                Handle(name=handle).full_clean()
            except ValidationError as e:
                st.error(e.messages[0], icon="")
                handle_style["border"] = "1px solid var(--bs-danger)"
            else:
                st.success("Handle is available", icon="")
                handle_style["border"] = "1px solid var(--bs-success)"

    if email := user.email:
        st.text_input("Email", value=email, disabled=True)
    if phone_number := user.phone_number:
        st.text_input(
            "Phone Number", value=phone_number.as_international, disabled=True
        )

    user.bio = st.text_area("Bio", value=user.bio)
    user.company = st.text_input("Company", value=user.company)
    user.github_username = st.text_input("GitHub Username", value=user.github_username)
    user.website_url = st.text_input("Website URL", value=user.website_url)

    error_msg: str | None = None
    try:
        user.full_clean()
    except ValidationError as e:
        error_msg = "\n\n".join(e.messages)

    if error_msg:
        st.error(error_msg, icon="⚠️")

    if st.button(
        "Save",
        type="primary",
        disabled=bool(error_msg),
    ):
        try:
            with transaction.atomic():
                if handle and not user.handle:
                    # user adds a new handle
                    user.handle = Handle(name=handle)
                    user.handle.save()
                elif handle and user.handle and user.handle.name != handle:
                    # user changes existing handle
                    user.handle.name = handle
                    user.handle.save()
                elif not handle and user.handle:
                    # user removes existing handle
                    user.handle.delete()
                    user.handle = None

                user.full_clean()
                user.save()
        except (ValidationError, IntegrityError) as e:
            for m in e.messages:
                st.error(m, icon="⚠️")
        else:
            st.success("Changes saved")


def _get_meta_title_for_profile(user: AppUser) -> str:
    title = user.display_name if user.display_name else user.handle.name
    if user.company:
        title += f" - {user.company[:15]}"

    title += f" {META_SEP} {META_TITLE_SUFFIX}"
    return title


def _get_meta_description_for_profile(user: AppUser) -> str:
    description = truncate_text_words(user.bio, maxlen=60)

    total_runs = get_run_count(user)
    if total_runs == 0:
        return description

    if description:
        description += f" {META_SEP} "

    description += f"{user.handle.name} has "

    public_runs_summary = get_public_runs_summary(user)
    contributions_summary = get_contributions_summary(user)

    activity_texts = []
    if public_runs_summary.total > 0:
        top_workflow_titles = make_natural_english_list(
            [
                str(workflow.short_title)
                for workflow in public_runs_summary.top_workflows
            ]
        )
        activity_texts.append(
            f"{public_runs_summary.total} public {top_workflow_titles} workflows"
        )

    if contributions_summary.total > 0:
        activity_texts.append(f"{contributions_summary.total} contributions")

    activity_texts.append(f"{total_runs} Gooey.AI runs.")

    description += make_natural_english_list(activity_texts)
    return description


def github_url_for_username(username: str) -> str:
    return f"https://github.com/{escape_html(username)}"


def get_profile_image(user: AppUser, placeholder_seed: str | None = None) -> str:
    return user.photo_url or get_placeholder_profile_image(placeholder_seed or user.uid)


def get_placeholder_profile_image(seed: str) -> str:
    hash = hashlib.md5(seed.encode()).hexdigest()
    return f"https://gravatar.com/avatar/{hash}?d=robohash&size=150"


def get_profile_title(user: AppUser) -> str:
    if user.display_name:
        return user.display_name
    elif user.email:
        return user.email.split("@")[0]
    elif user.phone_number:
        return user.phone_number.as_e164[:-4] + "XXXX"
    else:
        return ""


def make_natural_english_list(
    l: list[str],
    *,
    last_sep: str = " & ",
) -> str:
    match l:
        case []:
            return ""
        case [first]:
            return first
        case [first, last]:
            return f"{first}{last_sep}{last}"
        case [*rest, last]:
            text = ", ".join(rest)
            return f"{text}{last_sep}{last}"
        case _:
            raise ValueError("not a list")
