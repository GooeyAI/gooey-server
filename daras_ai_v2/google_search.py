import requests
import streamlit as st
from furl import furl

from daras_ai_v2 import settings


def call_scaleserp_rq(search_query: str, **kwargs) -> tuple[dict, list[str]]:
    kwargs.setdefault("include_fields", "related_questions")
    results = call_scaleserp(search_query, **kwargs)
    questions = [
        ques
        for rq in results.get("related_questions", [])
        if (ques := rq.get("question", "").strip())
    ]
    return results, questions


@st.cache_data(show_spinner=False)
def call_scaleserp(search_query: str, **kwargs) -> dict:
    scaleserp_url = furl(
        "https://api.scaleserp.com/search",
        query_params={
            "api_key": settings.SCALESERP_API_KEY,
            "q": search_query,
            **kwargs,
        },
    ).url

    r = requests.get(scaleserp_url)
    r.raise_for_status()

    scaleserp_results = r.json()
    return scaleserp_results
