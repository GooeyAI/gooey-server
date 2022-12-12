from firebase_admin import auth
from google.cloud import firestore
from google.cloud.firestore import DocumentReference
from google.cloud.firestore_v1.transaction import Transaction
from starlette.requests import Request

from auth_backend import ANONYMOUS_USER_COOKIE
from daras_ai.cache_tools import cache_and_refresh
from daras_ai_v2 import settings
from daras_ai_v2.base import get_doc_ref

FIREBASE_COLLECTION = "daras-ai--political_example"
USER_FIREBASE_COLLECTION = "users"


@cache_and_refresh
def list_all_docs():
    db = firestore.Client()
    db_collection = db.collection(USER_FIREBASE_COLLECTION)
    return db_collection.where("header_title", "!=", "").get()


def get_user_field(uid: str, field: str):
    user_doc = user_doc_ref(uid).get()
    return user_doc.get(field)


def add_user_credits(
    uid: str,
    credits_to_add: int,
):
    db = firestore.Client()
    transaction = db.transaction()
    users_ref = user_doc_ref(uid)
    update_credits_in_transaction(transaction, users_ref, abs(credits_to_add))


def deduct_user_credits(uid: str, credits_to_deduct: int):
    db = firestore.Client()
    transaction = db.transaction()
    users_ref = db.collection(USER_FIREBASE_COLLECTION).document(uid)
    update_credits_in_transaction(transaction, users_ref, -abs(credits_to_deduct))


@firestore.transactional
def update_credits_in_transaction(
    transaction: Transaction,
    users_ref: DocumentReference,
    credits: int,
):
    snapshot = users_ref.get(transaction=transaction)
    new_credits = snapshot.get("credits") + credits
    transaction.update(users_ref, {"credits": new_credits})


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

    doc_ref = user_doc_ref(uid)
    if not doc_ref.get().exists:
        doc_ref.create(default_data)

    return doc_ref.get().to_dict()


def user_doc_ref(uid: str) -> DocumentReference:
    return get_doc_ref(collection_id=USER_FIREBASE_COLLECTION, document_id=uid)
