import streamlit as st

from recipes.scale_serp import scaleserp_locations_list, scaleserp_image_sizes


def scaleserp_location_picker():
    defaults = st.session_state.get("scaleserp_locations", [])
    selected_countries = st.multiselect(
        "**ScaleSERP [Location](https://www.scaleserp.com/docs/search-api/reference/google-countries)**",
        options=scaleserp_locations_list,
        default=defaults,
    )
    st.session_state["scaleserp_locations"] = selected_countries


def scaleserp_image_size_picker():
    selected_image_size = st.selectbox(
        "**ScaleSERP [Image Size](https://www.scaleserp.com/docs/search-api/searches/google/images)**",
        options=scaleserp_image_sizes,
    )
    st.session_state["scaleserp_image_size"] = selected_image_size
