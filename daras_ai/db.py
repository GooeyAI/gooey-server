from google.cloud import firestore

from daras_ai.cache_tools import cache_and_refresh
from google.cloud.firestore_v1.transaction import Transaction
from google.cloud.firestore import DocumentReference

FIREBASE_COLLECTION = "daras-ai--political_example"
USER_FIREBASE_COLLECTION = "users"


@cache_and_refresh
def list_all_docs():
    db = firestore.Client()
    db_collection = db.collection(USER_FIREBASE_COLLECTION)
    return db_collection.where("header_title", "!=", "").get()


def get_user_field(uid: str, field: str):
    db = firestore.Client()
    db_collection = db.collection(USER_FIREBASE_COLLECTION)
    user_doc = db_collection.document(uid).get()
    return user_doc.get(field)


@firestore.transactional
def update_credits_in_transaction(
    transaction: Transaction,
    users_ref: DocumentReference,
    credits: int,
    deduct: bool = False,
):
    snapshot = users_ref.get(transaction=transaction)
    if deduct:
        new_credits = snapshot.get("credits") - credits
    else:
        new_credits = snapshot.get("credits") + credits
    transaction.update(users_ref, {"credits": new_credits})


def add_user_credits(
    uid: str,
    credits_to_add: int,
):
    db = firestore.Client()
    transaction = db.transaction()
    users_ref = db.collection(USER_FIREBASE_COLLECTION).document(uid)
    update_credits_in_transaction(transaction, users_ref, credits_to_add)


def deduct_user_credits(uid: str, credits_to_deduct: int):
    db = firestore.Client()
    transaction = db.transaction()
    users_ref = db.collection(USER_FIREBASE_COLLECTION).document(uid)
    update_credits_in_transaction(
        transaction, users_ref, credits_to_deduct, deduct=True
    )


def add_data_to_user_doc(uid: str, data_to_add: dict, new_doc: bool = False):
    db = firestore.Client()
    db_collection = db.collection(USER_FIREBASE_COLLECTION)
    user_doc_ref = db_collection.document(uid)
    if new_doc:
        user_doc_ref.set(data_to_add)
    else:
        user_doc_ref.update(data_to_add)


def search_user_by_stripe_customer_id(
    stripe_customer_id: str,
) -> str or None:
    db = firestore.Client()
    db_collection = db.collection(USER_FIREBASE_COLLECTION)
    user_doc_ref_list = db_collection.where(
        "stripe_customer_id", "==", stripe_customer_id
    ).get()
    if len(user_doc_ref_list) > 0:
        return user_doc_ref_list[0].get("uid")
    else:
        return None


# FIXME: Cannot get any other way to know doc exist or not.
def check_for_user_document_avail(uid: str) -> bool:
    db = firestore.Client()
    db_collection = db.collection(USER_FIREBASE_COLLECTION)
    user_doc_ref = db_collection.document(uid)
    return user_doc_ref.get().exists
