import requests
import streamlit as st
from furl import furl

from daras_ai_v2 import settings


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
