from concurrent.futures import ThreadPoolExecutor

from google.cloud import firestore

from app_users.models import AppUser, AppUserTransaction
from daras_ai_v2 import db


def run():
    with ThreadPoolExecutor(1000) as pool:
        for user in AppUser.objects.all():
            step1(pool, user.id, user.uid)


def step1(pool: ThreadPoolExecutor, user_id: int, uid: str):
    invoices = db.get_user_doc_ref(uid).collection("invoices").list_documents()
    for ref in invoices:
        pool.submit(step2, user_id, ref)


def step2(user_id: int, ref: firestore.DocumentReference):
    doc = ref.get().to_dict()
    print(doc)
    AppUserTransaction.objects.get_or_create(
        user_id=user_id,
        invoice_id=ref.id,
        defaults=dict(
            amount=doc.get("amount"),
            end_balance=doc.get("end_balance"),
            created_at=doc.get("timestamp"),
        ),
    )
