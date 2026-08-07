from __future__ import annotations

from django.db.models import Q, QuerySet

from app_users.models import AppUser

# Gooey team members who don't have a company email address.
TEAM_EMAILS = [
    "devxpy@gmail.com",
    "devxpy.spam@gmail.com",
    "sean@blagsvedt.com",
    "ambika@ajaibghar.com",
    "faraazmohd07@gmail.com",
]

TEAM_USER_Q = (
    Q(email__in=TEAM_EMAILS)
    | Q(email__endswith="gooey.ai")
    | Q(email__endswith="dara.network")
    | Q(email__endswith="jaaga.in")
)


def get_filtered_app_users(
    *,
    exclude_anon: bool = False,
    exclude_disabled: bool = False,
    exclude_team: bool = False,
    exclude_free: bool = False,
    exclude_paying: bool = False,
) -> QuerySet[AppUser]:
    qs = AppUser.objects.all()
    if exclude_anon:
        qs = qs.exclude(is_anonymous=True)
    if exclude_disabled:
        qs = qs.exclude(is_disabled=True)
    if exclude_team:
        qs = qs.exclude(TEAM_USER_Q)
    if exclude_free:
        qs = qs.filter(is_paying=True)
    if exclude_paying:
        qs = qs.exclude(is_paying=True)
    return qs
