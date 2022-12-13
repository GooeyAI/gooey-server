import stripe
from firebase_admin import auth
from google.cloud import firestore

from google.cloud.firestore import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
from starlette.requests import Request

from auth_backend import ANONYMOUS_USER_COOKIE
from daras_ai_v2 import settings

DEFAULT_COLLECTION = "daras-ai-v2"
USERS_COLLECTION = "users"

_db = firestore.Client()


def get_user_field(uid: str, field: str):
    user_doc = get_user_doc_ref(uid).get()
    return user_doc.get(field)


def update_user_credits(uid: str, amount: int, txn_id: str):
    transaction = _db.transaction()
    user_doc_ref = get_user_doc_ref(uid)
    _update_user_credits_in_txn(transaction, user_doc_ref, amount, txn_id)


@firestore.transactional
def _update_user_credits_in_txn(
    transaction: Transaction,
    user_doc_ref: DocumentReference,
    amount: int,
    txn_id: str,
):
    snapshot = user_doc_ref.get(transaction=transaction)

    # avoid updating twice
    try:
        last_txn_id = snapshot.get("last_txn_id")
    except KeyError:
        last_txn_id = None
    if last_txn_id == txn_id:
        return

    try:
        user_credits = snapshot.get("credits")
    except KeyError:
        user_credits = 0
    user_credits += amount

    transaction.update(user_doc_ref, {"credits": user_credits, "last_txn_id": txn_id})


def get_or_init_user_data(request: Request) -> dict:
    if request.user:
        user = request.user

        uid = user.uid
        default_data = {
            "credits": settings.LOGIN_USER_FREE_CREDITS,
            "anonymous_user": False,
        }
    else:
        if not request.session.get(ANONYMOUS_USER_COOKIE):
            request.session[ANONYMOUS_USER_COOKIE] = {
                "uid": auth.create_user().uid,
            }

        uid = request.session[ANONYMOUS_USER_COOKIE]["uid"]
        default_data = {
            "credits": settings.ANON_USER_FREE_CREDITS,
            "anonymous_user": True,
        }

    doc_ref = get_user_doc_ref(uid)
    if not doc_ref.get().exists:
        doc_ref.create(default_data)

    return doc_ref.get().to_dict()


def get_user_doc_ref(uid: str) -> DocumentReference:
    return get_doc_ref(collection_id=USERS_COLLECTION, document_id=uid)


def list_all_docs(
    collection_id=DEFAULT_COLLECTION,
    *,
    document_id: str = None,
    sub_collection_id: str = None,
) -> list:
    db = firestore.Client()
    db_collection = db.collection(collection_id)
    if sub_collection_id:
        doc_ref = db_collection.document(document_id)
        db_collection = doc_ref.collection(sub_collection_id)
    return db_collection.get()


def get_or_create_doc(
    doc_ref: firestore.DocumentReference,
) -> firestore.DocumentSnapshot:
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.create({})
        doc = doc_ref.get()
    return doc


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
