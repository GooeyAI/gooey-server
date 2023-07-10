from google.cloud import firestore

FIREBASE_SESSION_COOKIE = "firebase_session"
ANONYMOUS_USER_COOKIE = "anonymous_user"

DEFAULT_COLLECTION = "daras-ai-v2"
USERS_COLLECTION = "users"
API_KEYS_COLLECTION = "api_keys"

USER_BALANCE_FIELD = "balance"

EXAMPLES_COLLECTION = "examples"
USER_RUNS_COLLECTION = "user_runs"

USER_CHAT_HISTORY_COLLECTION = "user_chat_history"

CONNECTED_BOTS_COLLECTION = "connected_bots"

_client = None


def get_client():
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def get_doc_field(doc_ref: firestore.DocumentReference, field: str, default=None):
    snapshot = doc_ref.get([field])
    if not snapshot.exists:
        return default
    try:
        return snapshot.get(field)
    except KeyError:
        return default


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
    db_collection = get_client().collection(collection_id)
    doc_ref = db_collection.document(document_id)
    if sub_collection_id:
        sub_collection = doc_ref.collection(sub_collection_id)
        doc_ref = sub_collection.document(sub_document_id)
    return doc_ref
