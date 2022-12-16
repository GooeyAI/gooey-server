import math

import pandas as pd
import streamlit as st
from firebase_admin import auth

from daras_ai_v2 import db

# ref = get_doc_ref(
#     collection_id="users",
#     document_id="m0LMgTiNNwVdG7Rr9cxNJeqb1P42",
#     sub_collection_id="invoices",
#     sub_document_id="in_1MEXF3BBJIwZF3wz3adTPHT2",
# )
# st.write(ref.get().to_dict())
batch_size = 100

if "docs" not in st.session_state:
    with st.spinner("fetching users with runs..."):
        db_collection = db._db.collection("user_runs")
        st.session_state["docs"] = list(
            db_collection.list_documents(page_size=batch_size)
        )

doc_ids = [doc.id for doc in st.session_state["docs"]]
st.json(doc_ids, expanded=False)

users = st.session_state.setdefault("users", [])
if not users:
    with st.spinner("fetching users..."):
        for i in range(math.ceil(len(doc_ids) / batch_size)):
            doc_ids_batch = doc_ids[i * batch_size : (i + 1) * batch_size]
            doc_ids_batch = [auth.UidIdentifier(uid) for uid in doc_ids_batch]
            result = auth.get_users(doc_ids_batch)
            users.extend(result.users)

real_users = [
    user
    for user in st.session_state["users"]
    if (user.display_name or user.email or user.phone_number)
    and not (user.email.endswith("dara.network"))
    and not (user.email.endswith("gooey.ai"))
    and not (
        user.email
        in [
            "devxpy@gmail.com",
            "devxpy.spam@gmail.com",
        ]
    )
]

st.json(
    [f"{user.display_name} ({user.email or user.phone_number})" for user in real_users],
    expanded=False,
)

real_user_runs = st.session_state.setdefault("real_user_runs#1", [])
if not real_user_runs:
    for user in real_users:
        with st.spinner(
            f"fetching {user.display_name or user.email or user.phone_number}..."
        ):
            recipes = list(
                db._db.collection("user_runs").document(user.uid).collections()
            )
            total = {}
            for recipe in recipes:
                print(type(recipe))
                total[recipe.id] = len(recipe.select([]).get())
            real_user_runs.append((user, total))

real_user_runs.sort(key=lambda x: sum(x[1].values()), reverse=True)

st.write(
    pd.DataFrame.from_records(
        [
            {
                "name": f"{user.display_name} ({user.email or user.phone_number})",
                "Total": sum(runs.values()),
                **runs,
            }
            for user, runs in real_user_runs
        ],
    )
    .convert_dtypes()
    .fillna(0)
)
