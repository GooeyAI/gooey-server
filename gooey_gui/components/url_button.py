from gooey_gui.components import common as gui


def url_button(url):
    gui.anchor(
        '<i class="fa-regular fa-external-link-square"></i>',
        href=url,
        type="tertiary",
        new_tab=True,
        unsafe_allow_html=True,
    )
