import math

import pandas as pd
import plotly.express as px
import streamlit as st
from firebase_admin import auth
from google.cloud import firestore

from daras_ai_v2.face_restoration import map_parallel

st.set_page_config(layout="wide")

batch_size = 100
team_emails = [
    "devxpy@gmail.com",
    "devxpy.spam@gmail.com",
    "sean@blagsvedt.com",
]

user_runs = st.session_state.setdefault("user_runs", [])
if not user_runs:
    with st.spinner("fetching user IDs..."):
        db_collection = firestore.Client().collection("user_runs")
        user_runs.extend(db_collection.list_documents(page_size=batch_size))

all_user_ids = [doc.id for doc in user_runs]
st.json(all_user_ids, expanded=False)

all_users = st.session_state.setdefault("all_users", [])
if not all_users:
    with st.spinner("fetching users..."):
        for i in range(math.ceil(len(all_user_ids) / batch_size)):
            doc_ids_batch = all_user_ids[i * batch_size : (i + 1) * batch_size]
            doc_ids_batch = [auth.UidIdentifier(uid) for uid in doc_ids_batch]
            result = auth.get_users(doc_ids_batch)
            all_users.extend(result.users)

exclude_anon = st.checkbox("Exclude Anonymous", value=True)
if exclude_anon:
    all_users = [
        user
        for user in all_users
        if (user.display_name or user.email or user.phone_number)
    ]

exclude_team = st.checkbox("Exclude Team", value=True)
if exclude_team:
    all_users = [
        user
        for user in all_users
        if not (user.email.endswith("dara.network") or user.email.endswith("gooey.ai"))
        and not (user.email in team_emails)
    ]

st.json(
    [f"{user.display_name} ({user.email or user.phone_number})" for user in all_users],
    expanded=False,
)

user_runs = st.session_state.setdefault(f"user_runs#{exclude_anon}#{exclude_team}", [])
if not user_runs:
    with st.spinner(f"fetching user runs..."):

        def _fetch_total_runs(user: auth.UserRecord):
            recipes = list(
                firestore.Client()
                .collection("user_runs")
                .document(user.uid)
                .collections()
            )
            total = {}
            for recipe in recipes:
                total[recipe.id] = len(recipe.select([]).get())
            return user, total

        user_runs.extend(map_parallel(_fetch_total_runs, all_users))

user_runs.sort(key=lambda x: sum(x[1].values()), reverse=True)

df = (
    pd.DataFrame.from_records(
        [
            {
                "Name": user.display_name or "",
                "User": user.email or user.phone_number or user.uid or "",
                "All Recipes": sum(runs.values()),
                **runs,
            }
            for user, runs in user_runs
        ],
    )
    .convert_dtypes()
    .fillna(0)
)
st.write(df)


total_runs = df.sum().rename("Total Runs").to_frame().reset_index(names=["Recipe"])

col1, col2 = st.columns(2)

with col1:
    st.write(total_runs)

with col2:
    st.plotly_chart(
        px.pie(
            total_runs.iloc[1:],
            values="Total Runs",
            names="Recipe",
        ),
        use_container_width=True,
    )
