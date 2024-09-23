import datetime
import typing

from google.cloud import firestore

import gooey_gui as gui
from app_users.models import AppUser
from daras_ai_v2 import db
from daras_ai_v2.copy_to_clipboard_button_widget import (
    copy_to_clipboard_button,
)
from daras_ai_v2.crypto import (
    PBKDF2PasswordHasher,
    safe_preview,
    get_random_api_key,
)

if typing.TYPE_CHECKING:
    from workspaces.models import Workspace


def manage_api_keys(workspace: "Workspace", user: AppUser):
    gui.write(
        f"""
{workspace.display_name()} API keys are listed below.
Please note that we do not display your secret API keys again after you generate them.

Do not share your API key with others, or expose it in the browser or other client-side code.

In order to protect the security of your account,
Gooey.AI may also automatically rotate any API key that we've found has leaked publicly.
        """
    )

    db_collection = db.get_client().collection(db.API_KEYS_COLLECTION)
    api_keys = _load_api_keys(db_collection, workspace)

    table_area = gui.div()

    if gui.button("＋ Create new secret key"):
        doc = _generate_new_key_doc()
        doc["uid"] = user.uid
        doc["workspace_id"] = workspace.id
        api_keys.append(doc)
        db_collection.add(doc)

    with table_area:
        import pandas as pd

        gui.table(
            pd.DataFrame.from_records(
                columns=["Secret Key (Preview)", "Created At"],
                data=[
                    (
                        api_key["secret_key_preview"],
                        api_key["created_at"].strftime("%B %d, %Y at %I:%M:%S %p %Z"),
                    )
                    for api_key in api_keys
                ],
            ),
        )


def _load_api_keys(
    db_collection: firestore.CollectionReference, workspace: "Workspace"
):
    filter = firestore.FieldFilter("workspace_id", "==", workspace.id)
    if workspace.is_personal:
        # for backwards compatibility with existing keys
        filter = firestore.Or(
            [filter, firestore.FieldFilter("uid", "==", workspace.created_by.uid)]
        )

    return [
        snap.to_dict()
        for snap in db_collection.where(filter=filter).order_by("created_at").get()
    ]


def _generate_new_key_doc() -> dict:
    new_api_key = get_random_api_key()
    hasher = PBKDF2PasswordHasher()
    secret_key_hash = hasher.encode(new_api_key)
    created_at = datetime.datetime.utcnow()

    gui.success(
        f"""
##### API key generated

Please save this secret key somewhere safe and accessible.
For security reasons, **you won't be able to view it again** through your account.
If you lose this secret key, you'll need to generate a new one.
            """
    )
    col1, col2 = gui.columns([3, 1], responsive=False)
    with col1:
        gui.text_input(
            "recipe url",
            label_visibility="collapsed",
            disabled=True,
            value=new_api_key,
        )
    with col2:
        copy_to_clipboard_button(
            "📎 Copy Secret Key",
            value=new_api_key,
            style="height: 3.2rem",
        )

    return {
        "secret_key_hash": secret_key_hash,
        "secret_key_preview": safe_preview(new_api_key),
        "created_at": created_at,
    }
