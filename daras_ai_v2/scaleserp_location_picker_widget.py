import streamlit as st

from recipes.scale_serp import scaleserp_locations_list


def scaleserp_location_picker():
    defaults = st.session_state.get("scaleserp_locations", [])
    st.multiselect(
        "**ScaleSERP [Location](https://www.scaleserp.com/docs/search-api/reference/google-countries)**",
        options=scaleserp_locations_list,
        default=defaults,
        key="scaleserp_locations",
    )


def join_locations_to_str(scaleserp_locations: list[str] | None) -> str:
    if scaleserp_locations:
        return ",".join(scaleserp_locations)
    else:
        return "United States"
