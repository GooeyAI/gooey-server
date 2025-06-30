from app_users.models import AppUser


def is_user_workspace_owner(user: AppUser | None, workspace_filter: str | None) -> bool:
    """Check if the current user owns the filtered workspace."""
    if not (user and workspace_filter and not user.is_anonymous):
        return False

    user_workspace_ids = {w.id for w in user.cached_workspaces}
    user_workspace_handles = {w.handle.name for w in user.cached_workspaces if w.handle}

    try:
        # Check if workspace filter is numeric (workspace ID)
        workspace_id = int(workspace_filter)
        return workspace_id in user_workspace_ids
    except ValueError:
        # Workspace filter is a handle name
        return workspace_filter in user_workspace_handles
