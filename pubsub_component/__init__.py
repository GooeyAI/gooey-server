import streamlit.components.v1 as components


def pubusb_rerunner(url: str):
    _component(url=url)


_component = components.declare_component("pubusb_rerunner", path="./pubsub_component")
