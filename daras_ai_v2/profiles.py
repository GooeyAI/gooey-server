from html import escape as escape_html
from dataclasses import dataclass

from django.db.models import Count
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

import gooey_ui as st
from app_users.models import AppUser
from bots.models import PublishedRunVersion, SavedRun, Workflow
from daras_ai_v2.base import RedirectException, format_number_with_suffix
from handles.models import Handle


PLACEHOLDER_PROFILE_IMAGE = "https://via.placeholder.com/128"


@dataclass
class ContributionsSummary:
    total: int
    top_contributions: dict[Workflow, int]  # sorted dict


def user_profile_page(user: AppUser):
    user_profile_header(user)


def user_profile_header(user: AppUser):
    with st.div(className="mt-3"):
        col1, col2 = st.columns([2, 10])

    with col1, st.div(
        className="d-flex justify-content-center align-items-center h-100"
    ):
        profile_image(user, rounded=True)

    run_icon = '<i class="fa-regular fa-person-running"></i>'
    run_count = get_run_count(user)
    contribs = get_contributions_summary(user)

    with col2, st.div(
        className="d-flex flex-column justify-content-center align-items-center align-items-lg-start"
    ):
        with st.tag("h1", className="m-0"):
            st.html(escape_html(user.display_name))

        with st.tag("p", className="lead text-secondary mb-0"):
            st.html(escape_html(user.handle and user.handle.name or ""))

        with st.div(className="mt-3"):
            if user.github_username:
                with st.tag(
                    "span",
                    className="text-sm bg-light border border-dark rounded-pill px-2 py-1 me-4",
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
                    className="text-sm text-muted me-4",
                ), st.link(to=user.website_url, className="text-decoration-none"):
                    st.html(
                        '<i class="fa-solid fa-link"></i> '
                        + escape_html(
                            user.website_url.lstrip("https://").lstrip("http://")
                        )
                    )

            if user.company:
                with st.tag(
                    "span",
                    className="text-sm text-muted me-4",
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


def profile_image(user: AppUser, *, rounded=False):
    rounded_class = " rounded-circle" if rounded else ""
    st.image(
        user.photo_url or PLACEHOLDER_PROFILE_IMAGE,
        style={"width": "150px", "height": "150px"},
        className="me-0 me-lg-3 mb-3 mb-lg-0" + rounded_class,
    )


def edit_user_profile_page(user: AppUser):
    col1, col2 = st.columns([2, 10])
    with col1, st.div(className="w-100 h-100 d-flex justify-content-center"):
        profile_image(user)

    with col2:
        display_name = st.text_input("Name", value=user.display_name)
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

        bio = st.text_area("Bio", value=user.bio)
        company = st.text_input("Company", value=user.company)
        github_username = st.text_input("GitHub Username", value=user.github_username)
        website_url = st.text_input("Website URL", value=user.website_url)

        error_msg: str | None = None
        updated_fields: list[str] = []
        try:
            updated_fields = _validate_user_profile_changes(
                user,
                handle=handle,
                bio=bio,
                company=company,
                github_username=github_username,
                website_url=website_url,
            )
        except ValidationError as e:
            error_msg = "\n\n".join(e.messages)

        if error_msg:
            st.error(error_msg, icon="⚠️")

        col1, col2 = st.columns(2, responsive=False)
        with col1:
            save_button = st.button(
                "Save",
                type="primary",
                disabled=bool(error_msg or not updated_fields),
            )
        with (
            col2,
            st.div(className="d-flex justify-content-end"),
        ):
            if st.button("Logout", type="tertiary"):
                raise RedirectException("/logout/")

        if save_button:
            try:
                with transaction.atomic():
                    if "handle" in updated_fields:
                        user.handle.save()
                    user.full_clean()
                    user.save(update_fields=updated_fields)
            except (ValidationError, IntegrityError) as e:
                for m in e.messages:
                    st.error(m, icon="⚠️")
            else:
                st.success("Changes saved")


def _validate_user_profile_changes(
    user: AppUser,
    *,
    handle: str | None = None,
    display_name: str | None = None,
    bio: str | None = None,
    company: str | None = None,
    github_username: str | None = None,
    website_url: str | None = None,
) -> list[str]:
    """
    Returns updated fields

    Might raise ValidationError
    """
    updated_fields = []

    if handle and not user.handle:
        user.handle = Handle(name=handle)
        updated_fields.append("handle")
    elif handle and user.handle and user.handle.name != handle:
        user.handle.name = handle
        updated_fields.append("handle")

    updated_fields += set_changed_attrs(
        user,
        display_name=display_name,
        bio=bio,
        company=company,
        github_username=github_username,
        website_url=website_url,
    )

    user.full_clean()
    return updated_fields


def set_changed_attrs(
    obj,
    **possible_updates,
) -> list[str]:
    """
    Returns updated fields
    """
    updated_fields = []
    for k, v in possible_updates.items():
        if v is not None and getattr(obj, k) != v:
            setattr(obj, k, v)
            updated_fields.append(k)
    return updated_fields


def github_url_for_username(username: str) -> str:
    return f"https://github.com/{escape_html(username)}"
