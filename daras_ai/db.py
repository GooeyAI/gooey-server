from google.cloud import firestore

from daras_ai.cache_tools import cache_and_refresh

FIREBASE_COLLECTION = "daras-ai--political_example"


@cache_and_refresh
def list_all_docs():
    db = firestore.Client()
    db_collection = db.collection(FIREBASE_COLLECTION)
    return db_collection.where("header_title", "!=", "").get()
