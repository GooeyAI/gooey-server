import datetime
import typing

from firebase_admin import auth
from google.cloud import firestore
from google.cloud.firestore_v1.transaction import Transaction
from starlette.requests import Request

from daras_ai_v2 import settings

FB_PAGES_COLLECTION = "fb_pages"

FIREBASE_SESSION_COOKIE = "firebase_session"
ANONYMOUS_USER_COOKIE = "anonymous_user"

DEFAULT_COLLECTION = "daras-ai-v2"
USERS_COLLECTION = "users"
API_KEYS_COLLECTION = "api_keys"

USER_BALANCE_FIELD = "balance"

EXAMPLES_COLLECTION = "examples"
USER_RUNS_COLLECTION = "user_runs"

USER_CHAT_HISTORY_COLLECTION = "user_chat_history"

_db = firestore.Client()


def get_doc_field(doc_ref: firestore.DocumentReference, field: str, default=None):
    try:
        return doc_ref.get([field]).get(field)
    except KeyError:
        return default


def update_user_balance(uid: str, amount: int, invoice_id: str, **invoice_items):
    @firestore.transactional
    def _update_user_balance_in_txn(transaction: Transaction):
        user_doc_ref = get_user_doc_ref(uid)

        invoice_ref: firestore.DocumentReference
        invoice_ref = user_doc_ref.collection("invoices").document(invoice_id)
        # if an invoice entry exists
        if invoice_ref.get(transaction=transaction).exists:
            # avoid updating twice for same invoice
            return

        # get current balance
        try:
            balance = user_doc_ref.get(
                [USER_BALANCE_FIELD], transaction=transaction
            ).get(
                USER_BALANCE_FIELD,
            )
        except KeyError:
            balance = 0

        # update balance
        balance += amount
        transaction.update(user_doc_ref, {USER_BALANCE_FIELD: balance})

        # create invoice entry
        transaction.create(
            invoice_ref,
            {
                "amount": amount,
                "end_balance": balance,
                "timestamp": datetime.datetime.utcnow(),
                **invoice_items,
            },
        )

    _update_user_balance_in_txn(_db.transaction())


def get_or_init_user_data(request: Request) -> dict:
    if request.user:
        user = request.user

        uid = user.uid
        default_data = {
            USER_BALANCE_FIELD: settings.LOGIN_USER_FREE_CREDITS,
        }
    else:
        if not request.session.get(ANONYMOUS_USER_COOKIE):
            request.session[ANONYMOUS_USER_COOKIE] = {
                "uid": auth.create_user().uid,
            }

        uid = request.session[ANONYMOUS_USER_COOKIE]["uid"]
        default_data = {
            USER_BALANCE_FIELD: settings.ANON_USER_FREE_CREDITS,
        }

    doc_ref = get_user_doc_ref(uid)
    if not doc_ref.get().exists:
        doc_ref.create(default_data)

    return doc_ref.get().to_dict()


def get_user_doc_ref(uid: str) -> firestore.DocumentReference:
    return get_doc_ref(collection_id=USERS_COLLECTION, document_id=uid)


def get_or_create_doc(
    doc_ref: firestore.DocumentReference,
) -> firestore.DocumentSnapshot:
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.create({})
        doc = doc_ref.get()
    return doc


def get_collection_ref(
    collection_id=DEFAULT_COLLECTION,
    *,
    document_id: str = None,
    sub_collection_id: str = None,
) -> firestore.CollectionReference:
    db = firestore.Client()
    db_collection = db.collection(collection_id)
    if sub_collection_id:
        doc_ref = db_collection.document(document_id)
        db_collection = doc_ref.collection(sub_collection_id)
    return db_collection


def get_doc_ref(
    document_id: str,
    *,
    collection_id=DEFAULT_COLLECTION,
    sub_collection_id: str = None,
    sub_document_id: str = None,
) -> firestore.DocumentReference:
    db_collection = _db.collection(collection_id)
    doc_ref = db_collection.document(document_id)
    if sub_collection_id:
        sub_collection = doc_ref.collection(sub_collection_id)
        doc_ref = sub_collection.document(sub_document_id)
    return doc_ref


def get_page_access_token(page_id: str) -> str | None:
    doc_ref = get_fb_page_ref(page_id)
    return get_doc_field(doc_ref, "access_token")


def update_pages_for_user(page_docs_list: list[(str, dict)], uid: str):
    page_docs = dict(page_docs_list)
    batch = _db.batch()

    existing_user_pages = (
        _db.collection(FB_PAGES_COLLECTION).where("uid", "==", uid).get()
    )
    for snapshot in existing_user_pages:
        if snapshot.id in page_docs:
            # update page data because it belongs to same user
            batch.update(snapshot.reference, page_docs.pop(snapshot.id))
        else:
            # delete pages that are not longer connected
            batch.delete(snapshot.reference)

    for page_id, page_doc in page_docs.items():
        # create / overwrite data for new pages
        batch.set(get_fb_page_ref(page_id), page_doc)

    batch.commit()


def get_fb_page_ref(page_id):
    return _db.collection(FB_PAGES_COLLECTION).document(page_id)


def get_user_msgs(*, bot_id: str, user_id: str) -> list:
    doc_ref = get_doc_ref(
        collection_id=USER_CHAT_HISTORY_COLLECTION,
        document_id=f"{bot_id}:{user_id}",
    )
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get("messages", [])
    return []


def save_user_msgs(
    *,
    bot_id: str,
    user_id: str,
    messages: list,
    platform: typing.Literal["fb", "ig", "wa"],
):
    doc_ref = get_doc_ref(
        collection_id=USER_CHAT_HISTORY_COLLECTION,
        document_id=f"{bot_id}:{user_id}",
    )
    doc_ref.set(
        {
            "platform": platform,
            "bot_id": bot_id,
            "user_id": user_id,
            "messages": messages,
        }
    )
