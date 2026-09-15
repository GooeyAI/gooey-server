import html

import gooey_gui as gui

from app_users.models import AppUser
from bots.models import PublishedRun, SavedRun
from daras_ai_v2 import icons
from daras_ai_v2.fastapi_tricks import get_route_path
from gooey_gui.types.run_debug_info_props import AuthorProps
from workspaces.models import Workspace


def render_author_as_breadcrumb(
    user: AppUser | None,
    pr: PublishedRun,
    sr: SavedRun,
    current_workspace: Workspace | None = None,
):
    is_example = pr.saved_run_id == sr.id
    if is_example:
        workspace = pr.workspace
    else:
        workspace = sr.workspace

    with gui.div(
        className="d-flex gap-2 align-items-center", style=dict(listStyle="none")
    ):
        with gui.tag("li"):
            render_author_from_workspace(workspace, current_workspace=current_workspace)

        # don't render the user's name for examples and personal workspaces
        if is_example or not workspace or workspace.is_personal:
            return

        gui.html(icons.chevron_right)

        with gui.tag(
            "li", className="d-flex align-items-center container-margin-reset"
        ):
            if user:
                full_name = user.full_name()
                handle = user.get_handle()
                link = handle and handle.get_app_url()
            else:
                full_name = "Deleted User"
                link = None

            linkto = link and gui.link(to=link) or gui.dummy()
            with linkto:
                gui.caption(full_name)


def render_author_from_workspace(
    workspace: Workspace | None,
    *,
    image_size: str = "30px",
    responsive: bool = True,
    show_as_link: bool = True,
    current_workspace: Workspace | None = None,
):
    if not workspace:
        return
    return render_author(
        workspace_author(
            workspace, show_as_link=show_as_link, current_workspace=current_workspace
        ),
        image_size=image_size,
        responsive=responsive,
    )


def render_author_from_user(
    user: AppUser | None,
    *,
    image_size: str = "30px",
    responsive: bool = True,
    show_as_link: bool = True,
):
    if not user:
        return
    return render_author(
        user_author(user, show_as_link=show_as_link),
        image_size=image_size,
        responsive=responsive,
    )


def workspace_author(
    workspace: Workspace,
    *,
    show_as_link: bool = True,
    current_workspace: Workspace | None = None,
) -> AuthorProps:
    from routers.account import saved_route

    photo = workspace.get_photo()
    if workspace.is_personal:
        name = workspace.created_by.display_name
    else:
        name = workspace.display_name()

    if show_as_link and workspace == current_workspace:
        link = get_route_path(saved_route)
    elif show_as_link and workspace.handle_id:
        link = workspace.handle.get_app_url()
    else:
        link = None
    return AuthorProps(name=name, photo_url=photo, url=link)


def user_author(user: AppUser, *, show_as_link: bool = True) -> AuthorProps:
    if show_as_link and (handle := user.get_handle()):
        link = handle.get_app_url()
    else:
        link = None
    return AuthorProps(name=user.full_name(), photo_url=user.get_photo(), url=link)


def render_author(
    author: AuthorProps,
    *,
    image_size: str,
    responsive: bool,
):
    photo, name, link = author.photo_url, author.name, author.url
    if not photo and not name:
        return

    if responsive:
        responsive_image_size = f"calc({image_size} * 0.67)"
    else:
        responsive_image_size = image_size

    linkto = link and gui.link(to=link) or gui.dummy()
    with linkto, gui.div(className="d-flex align-items-center"):
        if photo:
            with gui.styled(
                """
                @media (min-width: 1024px) {
                    & {
                        width: %(image_size)s;
                        height: %(image_size)s;
                    }
                }
                """
                % dict(image_size=image_size)
            ):
                gui.image(
                    photo,
                    style=dict(
                        width=responsive_image_size,
                        height=responsive_image_size,
                        marginRight="6px",
                        borderRadius="50%",
                        objectFit="cover",
                        pointerEvents="none",
                    ),
                )

        if name:
            with gui.tag("span", className="author-name"):
                gui.html(html.escape(name))
