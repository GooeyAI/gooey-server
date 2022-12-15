import streamlit.components.v1 as components


def st_call_js(code):
    js = components.declare_component(
        "js",
        path="./st_call_js",
        # url="http://localhost:3001",
    )
    return js(code=code)
