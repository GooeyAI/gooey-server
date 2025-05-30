import html

import gooey_gui as gui

from app_users.models import AppUser
from bots.models import PublishedRun, SavedRun
from daras_ai_v2 import icons
from workspaces.models import Workspace


def render_author_as_breadcrumb(
    user: AppUser | None,
    pr: PublishedRun,
    sr: SavedRun,
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
            render_author_from_workspace(workspace)

        # don't render the user's name for examples and personal workspaces
        if is_example or workspace.is_personal:
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
):
    if not workspace:
        return
    photo = workspace.get_photo()
    if workspace.is_personal:
        name = workspace.created_by.display_name
    else:
        name = workspace.display_name()
    if show_as_link and workspace.handle_id:
        link = workspace.handle.get_app_url()
    else:
        link = None
    return render_author(
        photo=photo,
        name=name,
        link=link,
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
    photo = user.get_photo()
    name = user.full_name()
    if show_as_link and (handle := user.get_handle()):
        link = handle.get_app_url()
    else:
        link = None
    return render_author(
        photo=photo,
        name=name,
        link=link,
        image_size=image_size,
        responsive=responsive,
    )


def render_author(
    photo: str | None,
    name: str | None,
    link: str | None,
    *,
    image_size: str,
    responsive: bool,
):
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
