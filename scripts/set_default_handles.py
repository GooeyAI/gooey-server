from loguru import logger

from workspaces.models import Workspace
from handles.models import Handle


def run():
    team_workspaces = Workspace.objects.filter(is_personal=False, handle__isnull=True)

    for workspace in team_workspaces:
        if handle := Handle.create_default_for_workspace(workspace):
            workspace.handle = handle
            workspace.save()
        else:
            logger.warning(
                f"unable to find acceptable handle for workspace: {workspace}"
            )
