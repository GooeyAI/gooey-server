import gooey_gui as gui
from workspaces.models import Workspace
from workspaces.views import member_invite_button_with_dialog
from widgets.author import render_author_from_workspace


def render_workspace_with_invite_button(workspace: Workspace, user_id: int) -> None:
    """
    Renders a workspace with an invite button in a two-column layout.
    
    Args:
        workspace: The workspace to render
        user_id: The ID of the current user
    """
    col1, col2 = gui.columns([9, 3], responsive=False)
    with col1:
        with gui.tag("p", className="mb-1 text-muted"):
            gui.html("WORKSPACE")
        render_author_from_workspace(workspace)
    with col2:
        try:
            membership = workspace.memberships.get(user_id=user_id)
        except Workspace.DoesNotExist:
            return
        member_invite_button_with_dialog(
            membership,
            close_on_confirm=False,
            type="tertiary",
            className="mb-0",
        ) 