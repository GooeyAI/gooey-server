import datetime

from google.cloud import firestore

DEFAULT_COLLECTION = "daras-ai-v2"
USERS_COLLECTION = "users"

USER_BALANCE_FIELD = "balance"

_db = firestore.Client()


def get_doc_field(
    doc_ref: firestore.DocumentReference,
    field: str,
    *,
    default=None,
    transaction: firestore.Transaction = None,
):
    doc = doc_ref.get([field], transaction=transaction)
    if not doc.exists:
        return default
    try:
        return doc.get(field)
    except KeyError:
        return default


def update_user_balance(*, uid: str, amount: int, invoice_id: str):
    @firestore.transactional
    def _update_user_balance_in_txn(transaction: firestore.Transaction):
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
            },
        )

    _update_user_balance_in_txn(_db.transaction())


def get_user_doc_ref(uid: str) -> firestore.DocumentReference:
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
