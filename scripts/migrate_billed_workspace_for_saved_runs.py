from django.db import connection
from loguru import logger


def run():
    with connection.cursor() as cursor:
        cursor.execute(
            """
        UPDATE bots_savedrun
        SET billed_workspace_id = workspaces_workspace.id
        FROM
            workspaces_workspace INNER JOIN
            app_users_appuser ON workspaces_workspace.created_by_id = app_users_appuser.id
        WHERE
            bots_savedrun.billed_workspace_id IS NULL AND
            bots_savedrun.uid IS NOT NULL AND
            bots_savedrun.uid = app_users_appuser.uid AND
            workspaces_workspace.is_personal = true
        """
        )
        rows_updated = cursor.rowcount

    logger.info(f"Updated {rows_updated} saved runs with billed workspace")
