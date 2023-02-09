import datetime
from multiprocessing.pool import ThreadPool

from google.cloud.firestore_v1 import DocumentReference

from daras_ai_v2 import db

num_workers = 1000
all_user_runs = {}
old_runs = db.get_collection_ref(collection_id="user_runs")
new_runs = db.get_collection_ref(collection_id="user_runs_combined")


def main():
    with ThreadPool(num_workers) as pool:
        users = list(old_runs.list_documents())
        print("users:", len(users))

        pages = flatten(pool.map(lambda user: list(user.collections()), users))
        print("pages:", len(pages))

        runs = flatten(pool.map(lambda page: list(page.list_documents()), pages))
        print("runs:", len(runs))

        pool.map(save_run, runs)
        print("total:", len(all_user_runs))


def save_run(run: DocumentReference):
    page_id = run.parent.id
    uid = run.parent.parent.id

    doc = run.get().to_dict()
    new_doc_id = ":".join([page_id, uid, run.id])

    updated_at = doc.pop("updated_at", None)
    if isinstance(updated_at, str):
        updated_at = datetime.datetime.fromisoformat(updated_at)

    new_doc = {
        "uid": uid,
        "page_id": page_id,
        "run_id": run.id,
        #
        "title": doc.pop("__title", None),
        "description": doc.pop("__notes", None),
        "notes": None,
        "citations": None,
        #
        "run_time": 0,
        "created_at": None,
        "updated_at": updated_at,
        "error_msg": doc.pop("__error_msg", None),
        #
        "invoice_id": None,
        "api_key_id": None,
        #
        "state": doc,
    }

    all_user_runs[new_doc_id] = new_doc
    print(new_doc_id, len(all_user_runs))

    new_doc_ref = new_runs.document(new_doc_id)
    new_doc_ref.set(new_doc)


def flatten(l1):
    return [it for l2 in l1 for it in l2]


if __name__ == "__main__":
    main()
