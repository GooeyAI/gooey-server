import hashlib
from html import escape as escape_html
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.db import IntegrityError, transaction

import gooey_ui as st
from app_users.models import AppUser
from bots.models import (
    PublishedRun,
    PublishedRunVersion,
    PublishedRunVisibility,
    SavedRun,
    Workflow,
)
from daras_ai_v2.base import RedirectException, format_number_with_suffix
from daras_ai_v2.grid_layout_widget import grid_layout
from handles.models import Handle


@dataclass
class ContributionsSummary:
    total: int
    top_contributions: dict[Workflow, int]  # sorted dict


def user_profile_page(user: AppUser):
    user_profile_header(user)
    st.html("\n<hr>\n")
    user_profile_main_content(user)


def user_profile_header(user: AppUser):
    with st.div(className="mt-3"):
        col1, col2 = st.columns([2, 10])

    with col1, st.div(
        className="d-flex justify-content-center align-items-center h-100"
    ):
        profile_image(
            user.photo_url,
            placeholder_seed=user.uid,
            className="rounded-circle",
        )

    run_icon = '<i class="fa-regular fa-person-running"></i>'
    run_count = get_run_count(user)
    contribs = get_contributions_summary(user)

    with col2, st.div(
        className="d-flex text-center flex-column justify-content-center align-items-center align-items-lg-start"
    ):
        with st.tag("h1", className="m-0"):
            st.html(escape_html(user.display_name))

        with st.tag("p", className="lead text-secondary mb-0"):
            st.html(escape_html(user.handle and user.handle.name or ""))

        if user.bio:
            with st.div(className="mt-2 text-secondary"):
                st.html(escape_html(user.bio))

        with st.div(className="mt-3"):
            if user.github_username:
                with st.tag(
                    "span",
                    className="text-sm bg-light border border-dark rounded-pill px-2 py-1 me-4 d-inline-block mb-1",
                ), st.link(
                    to=github_url_for_username(user.github_username),
                    className="text-decoration-none",
                ):
                    st.html(
                        '<i class="fa-brands fa-github"></i> '
                        + escape_html(user.github_username)
                    )

            if user.website_url:
                with st.tag(
                    "span",
                    className="text-sm me-4 d-inline-block mb-1",
                ), st.link(to=user.website_url):
                    st.html(
                        '<i class="fa-solid fa-link"></i> '
                        + escape_html(
                            user.website_url.lstrip("https://").lstrip("http://")
                        )
                    )

            if user.company:
                with st.tag(
                    "span",
                    className="text-sm text-muted me-4 d-inline-block mb-1",
                ):
                    st.html(
                        '<i class="fa-solid fa-buildings"></i> '
                        + escape_html(user.company)
                    )

        st.html(
            f"""\
<div class="d-flex mt-3">
    <div class="me-3 text-secondary">
        {run_icon} {escape_html(format_number_with_suffix(run_count))} runs
    </div>

    <div>
        <div>{contribs.total} contributions since joining</div>
        <small class="mt-1">
            {", ".join(
                f"{escape_html(workflow.short_title)} ({count})"
                for workflow, count in contribs.top_contributions.items()
            )}
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
        with st.div(className="mb-2"), st.tag(
            "span", className="bg-light text-dark px-2 py-1 rounded-pill"
        ):
            st.html(escape_html(workflow.short_title))

        page_cls = workflow.page_cls
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


def profile_image(url: str, placeholder_seed: str, **props):
    style = {"width": "150px", "height": "150px", "object-fit": "cover"} | props.get(
        "style", {}
    )
    st.image(
        url or get_placeholder_profile_image(placeholder_seed),
        style=style,
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
    colspec = [2, 10] if not _is_uploading_photo() else [6, 6]
    photo_col, form_col = st.columns(colspec)

    with photo_col:
        _edit_user_profile_photo_section(user)
    with form_col:
        _edit_user_profile_form_section(user)


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
                    '<i class="fa-solid fa-xmark-large"></i> Cancel',
                    className="text-danger",
                ):
                    _set_is_uploading_photo(False)
                    st.experimental_rerun()

            with image_div:
                profile_image(image_url or user.photo_url, placeholder_seed=user.uid)
        else:
            profile_image(user.photo_url, placeholder_seed=user.uid)
            if user.photo_url and st.button(
                "Clear Photo", type="link", className="text-decoration-none px-2 py-1"
            ):
                _set_new_profile_photo(user, "")
                st.experimental_rerun()
            if st.button(
                "Upload Photo", type="link", className="text-decoration-none px-2 py-1"
            ):
                _set_is_uploading_photo(True)
                st.experimental_rerun()


def _edit_user_profile_form_section(user: AppUser):
    user.display_name = st.text_input("Name", value=user.display_name)

    handle_style: dict[str, str] = {}
    if handle := st.text_input(
        "Handle",
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
        st.text_input("Phone Number", value=phone_number, disabled=True)

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

    col1, col2 = st.columns(2, responsive=False)
    with col1:
        save_button = st.button(
            "Save",
            type="primary",
            disabled=bool(error_msg),
        )
    with (
        col2,
        st.div(className="d-flex justify-content-end align-items-center h-100"),
        st.tag("a", href="/logout/"),
    ):
        st.caption("Sign out")

    if save_button:
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

                user.full_clean()
                user.save()
        except (ValidationError, IntegrityError) as e:
            for m in e.messages:
                st.error(m, icon="⚠️")
        else:
            st.success("Changes saved")


def github_url_for_username(username: str) -> str:
    return f"https://github.com/{escape_html(username)}"


def get_placeholder_profile_image(seed: str) -> str:
    hash = hashlib.md5(seed.encode()).hexdigest()
    return f"https://gravatar.com/avatar/{hash}?d=robohash&size=150"
