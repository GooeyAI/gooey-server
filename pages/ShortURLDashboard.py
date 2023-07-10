from gooeysite import wsgi

assert wsgi

import streamlit as st

st.set_page_config(layout="wide")

from bots.models import ShortenedURLs, Workflow, SavedRun
from urllib.parse import urlparse
import pandas as pd


def main():
    st.markdown(
        """
        # Gooey.AI Short URL Dashboard
        """
    )
    workflow = st.selectbox(
        "Workflow",
        options=[None] + [w for w in Workflow],
        format_func=lambda w: w.name if w else "---",
    )
    shorturl = st.text_input("Short URL")
    longurl = st.text_input("Long URL")
    run = st.selectbox(
        "Run (most recent 100 shown))",
        options=[None]
        + list(
            SavedRun.objects.filter(
                pk__in=ShortenedURLs.objects.values_list("run", flat=True).distinct()[
                    :100
                ]
            )
        ),
        format_func=lambda r: str(r) if r else "---",
    )
    num_results = st.number_input("Max number of results", value=100)
    if workflow or shorturl or longurl or run:
        with st.spinner("Loading stats..."):
            query = ShortenedURLs.objects.all()
            if workflow:
                query = query.filter(run__workflow=workflow)
            if shorturl:
                query = query.filter(
                    shortened_guid=urlparse(shorturl).path.replace("/", "")
                )
            if longurl:
                query = query.filter(url__icontains=longurl)
            if run:
                query = query.filter(run=run)
            df_run = pd.DataFrame(
                list(
                    SavedRun.objects.filter(
                        pk__in=query.values_list("run", flat=True).distinct()
                    ).values()
                )
            )
            df = pd.DataFrame(list(query[:num_results].values())).merge(
                df_run, how="left", left_on="run_id", right_on="id"
            )
            df.drop(columns=["run_id_x", "id_y"], inplace=True)
            df.rename(columns={"id_x": "id", "run_id_y": "run_id"}, inplace=True)
            st.table(df)
            st.download_button(
                "Download as csv", df.to_csv().encode("utf-8"), "file.csv", "text/csv"
            )


if __name__ == "__main__":
    main()
