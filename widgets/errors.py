import gooey_gui as gui

from daras_ai_v2 import settings
from daras_ai_v2.fastapi_tricks import get_app_route_url, get_route_path
from routers.account import account_route
from workspaces.widgets import set_current_workspace


def insufficient_credits_error(error_params: dict):
    from daras_ai_v2.base import SUBMIT_AFTER_LOGIN_Q

    RERUN_KEY = "--insufficient-credits-rerun"
    UPGRADE_KEY = "--insufficient-credits-upgrade"
    BUY_CREDITS_KEY = "--insufficient-credits-buy-personal"

    request = error_params["request"]
    sr = error_params["sr"]
    current_workspace = error_params.get("current_workspace")
    price = error_params.get("price", None)
    current_user = request.user
    personal_workspace = (
        current_user and current_user.get_or_create_personal_workspace()[0]
    )

    show_upgrade = False

    if (
        not current_user
        or not sr.workspace
        or sr.workspace not in current_user.cached_workspaces
    ):
        title = "Run failed (Not enough credits)"
        rerun_workspace = current_workspace

    elif current_user.uid == sr.uid and len(current_user.cached_workspaces) <= 1:
        title = "You've run out of Gooey.AI credits"
        rerun_workspace = personal_workspace

    else:
        title = (
            f"You've run out of credits in {sr.workspace.display_name(current_user)}"
        )
        rerun_workspace = personal_workspace
        if not sr.workspace.is_personal and current_user in sr.workspace.get_admins():
            show_upgrade = True

    if not rerun_workspace:
        rerun_workspace_name = None
    elif rerun_workspace.is_personal:
        rerun_workspace_name = "Personal"
    else:
        rerun_workspace_name = rerun_workspace.display_name(current_user)

    show_rerun = rerun_workspace and rerun_workspace.balance >= (price or 1)
    is_anonymous = not current_user or current_user.is_anonymous
    if is_anonymous:
        account_url = get_app_route_url(
            account_route,
            query_params={
                "next": sr.get_app_url(query_params={SUBMIT_AFTER_LOGIN_Q: "1"}),
            },
        )
    else:
        account_url = get_app_route_url(account_route)

    if gui.session_state.pop(RERUN_KEY, None):
        if rerun_workspace:
            set_current_workspace(request.session, rerun_workspace.id)
        gui.session_state["-submit-workflow"] = True
        raise gui.RerunException()

    if gui.session_state.pop(BUY_CREDITS_KEY, None):
        if rerun_workspace:
            set_current_workspace(request.session, rerun_workspace.id)
        raise gui.RedirectException(get_route_path(account_route))

    if gui.session_state.pop(UPGRADE_KEY, None):
        if sr:
            set_current_workspace(request.session, sr.workspace_id)
        raise gui.RedirectException(get_route_path(account_route))

    gui.component(
        "InsufficientCredits",
        accountUrl=account_url,
        isAnonymous=is_anonymous,
        verifiedEmailUserFreeCredits=settings.VERIFIED_EMAIL_USER_FREE_CREDITS,
        rerunKey=RERUN_KEY,
        upgradeKey=UPGRADE_KEY,
        buyCreditsKey=BUY_CREDITS_KEY,
        price=price,
        title=title,
        showUpgrade=show_upgrade,
        showRerun=bool(show_rerun),
        rerunWorkspaceBalance=(rerun_workspace.balance if rerun_workspace else None),
        rerunWorkspaceName=rerun_workspace_name,
    )
