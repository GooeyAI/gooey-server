from firebase_admin import auth
from google.cloud import firestore
from google.cloud.firestore import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
from starlette.requests import Request

from auth_backend import ANONYMOUS_USER_COOKIE
from daras_ai_v2 import settings

DEFAULT_COLLECTION = "daras-ai-v2"
USERS_COLLECTION = "users"


def get_user_field(uid: str, field: str):
    user_doc = get_user_doc_ref(uid).get()
    return user_doc.get(field)


def add_user_credits(
    uid: str,
    credits_to_add: int,
):
    db = firestore.Client()
    transaction = db.transaction()
    user_doc_ref = get_user_doc_ref(uid)
    update_credits_in_transaction(transaction, user_doc_ref, abs(credits_to_add))


def deduct_user_credits(uid: str, credits_to_deduct: int):
    db = firestore.Client()
    transaction = db.transaction()
    user_doc_ref = get_user_doc_ref(uid)
    update_credits_in_transaction(transaction, user_doc_ref, -abs(credits_to_deduct))


@firestore.transactional
def update_credits_in_transaction(
    transaction: Transaction,
    user_doc_ref: DocumentReference,
    amount: int,
):
    snapshot = user_doc_ref.get(transaction=transaction)
    new_credits = snapshot.get("credits") + amount
    transaction.update(user_doc_ref, {"credits": new_credits})


# def search_user_by_stripe_customer_id(
#     stripe_customer_id: str,
# ) -> str or None:
#     db = firestore.Client()
#     db_collection = db.collection(USER_FIREBASE_COLLECTION)
#     user_doc_ref_list = list(
#         db_collection.where("stripe_customer_id", "==", stripe_customer_id).get()
#     )
#     if not user_doc_ref_list:
#         return None
#     return user_doc_ref_list[0].get("uid")


def get_or_init_user_data(request: Request) -> dict:
    if request.user:
        user = request.user

        uid = user.uid
        default_data = {
            "credits": settings.LOGIN_USER_FREE_CREDITS,
            "lookup_key": None,
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
            "lookup_key": None,
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
    db = firestore.Client()
    db_collection = db.collection(collection_id)
    doc_ref = db_collection.document(document_id)
    if sub_collection_id:
        sub_collection = doc_ref.collection(sub_collection_id)
        doc_ref = sub_collection.document(sub_document_id)
    return doc_ref
