from app_users.models import AppUser


def is_user_workspace_owner(user: AppUser | None, workspace_filter: str | None) -> bool:
    """
    Check if the current user owns the filtered workspace.

    This function determines workspace ownership by checking if the provided workspace
    filter matches any of the user's associated workspaces. It supports two workspace
    filter formats and implements caching for performance optimization.

    Args:
        user: The user to check ownership for. Returns False if None or anonymous.
              Must have a 'cached_workspaces' attribute containing workspace objects.
        workspace_filter: Either a workspace ID (numeric string) or handle name (string).
                         - Numeric strings (e.g., "123") are treated as workspace IDs
                         - Non-numeric strings (e.g., "my-workspace") are treated as handle names
                         Returns False if None or empty after stripping whitespace.

    Returns:
        True if the user owns the workspace identified by the filter, False otherwise.
        Returns False for any invalid input, malformed data, or exceptions.

    Performance Notes:
        - Uses caching to avoid recreating workspace sets on repeated calls
        - First call creates '_workspace_ids_cache' and '_workspace_handles_cache' on user object
        - Subsequent calls use cached sets for O(1) lookup performance

    Supported Workspace Filter Formats:
        - Workspace ID: "123", "456" (numeric strings converted to int)
        - Handle name: "my-workspace", "team-handle" (string literals)
        - Invalid: None, "", "  ", non-string types (all return False)

    Exception Handling:
        - Gracefully handles malformed user data or workspace attributes
        - Catches conversion errors for invalid numeric strings
        - Returns False for any unexpected exceptions to prevent crashes
    """
    if not (user and workspace_filter and not user.is_anonymous):
        return False

    # Additional input validation
    if not isinstance(workspace_filter, str):
        return False

    workspace_filter = workspace_filter.strip()
    if not workspace_filter:
        return False

    try:
        # Cache workspace sets to avoid recreating on every call
        if not hasattr(user, "_workspace_ids_cache"):
            user._workspace_ids_cache = {w.id for w in user.cached_workspaces}
            user._workspace_handles_cache = {
                w.handle.name
                for w in user.cached_workspaces
                if w.handle and hasattr(w.handle, "name") and w.handle.name
            }

        user_workspace_ids = user._workspace_ids_cache
        user_workspace_handles = user._workspace_handles_cache
    except (AttributeError, TypeError):
        # Handle cases where user.cached_workspaces or workspace attributes are malformed
        return False

    try:
        # Check if workspace filter is numeric (workspace ID)
        workspace_id = int(workspace_filter)
        return workspace_id in user_workspace_ids
    except (ValueError, TypeError, OverflowError):
        # ValueError: invalid literal for int()
        # TypeError: int() argument must be a string or number
        # OverflowError: int too large to convert
        pass
    except Exception:
        # Catch any other unexpected exceptions during int conversion
        return False

    try:
        # Workspace filter is a handle name
        return workspace_filter in user_workspace_handles
    except (TypeError, AttributeError):
        # Handle cases where membership check fails due to type issues
        return False
    except Exception:
        # Catch any other unexpected exceptions during membership check
        return False
