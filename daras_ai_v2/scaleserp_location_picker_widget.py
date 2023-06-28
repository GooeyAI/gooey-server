import gooey_ui as st

from recipes.scale_serp import scaleserp_locations_list


def scaleserp_location_picker():
    st.multiselect(
        "**ScaleSERP [Location](https://www.scaleserp.com/docs/search-api/reference/google-countries)**",
        options=scaleserp_locations_list,
        key="scaleserp_locations",
    )
