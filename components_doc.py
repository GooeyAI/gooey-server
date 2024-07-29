import inspect
from functools import wraps

import gooey_gui as gui

META_TITLE = "Gooey Components"
META_DESCRIPTION = "Explore the Gooey Component Library"

TITLE = "Gooey AI - Component Library"
DESCRIPTION = "See & Learn for yourself"


def render():
    heading(title=TITLE, description=DESCRIPTION)

    with gui.tag(
        "div",
        className="mt-4 container-fluid",
    ):
        render_layouts()
        render_content()
        render_components()


def show_source_code(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        out = fn(*args, **kwargs)
        code_block(inspect.getsource(fn))
        return out

    return wrapper


def render_layouts():
    section_title("Layouts")

    # Full Width Layout
    sub_section_title("Full Width Layout")
    full_width_layout()

    # 1/2 Layout
    sub_section_title("Full Width 1/2 Layout")
    half_width_layout()

    # 1/3 Layout
    sub_section_title("Full Width 1/3 Layout")
    third_width_layout()

    # Responsive 1/3 Layout
    sub_section_title("Responsive 1/3 Layout")
    gui.write("These columns will go full width on small devices")
    responsive_third_width_layout()


@show_source_code
def full_width_layout():
    with gui.div(className="w-100 bg-light p-4"):
        gui.html("This is a full width layout")


@show_source_code
def half_width_layout():
    col1, col2 = gui.columns(2, responsive=False)
    with col1:
        with gui.div(className="border"):
            gui.html("This is a 1/2 width layout")
    with col2:
        with gui.div(className="border"):
            gui.html("This is a 1/2 width layout")


@show_source_code
def third_width_layout():
    col1, col2, col3 = gui.columns(3, responsive=False)
    with col1:
        with gui.div(className="border"):
            gui.html("This is a 1/3 width layout")
    with col2:
        with gui.div(className="border"):
            gui.html("This is a 1/3 width layout")
    with col3:
        with gui.div(className="border"):
            gui.html("This is a 1/3 width layout")


@show_source_code
def responsive_third_width_layout():
    col1, col2, col3 = gui.columns(3)
    with col1:
        with gui.div(className="border"):
            gui.html("This is a responsive 1/3 width layout")
    with col2:
        with gui.div(className="border"):
            gui.html("This is a responsive 1/3 width layout")
    with col3:
        with gui.div(className="border"):
            gui.html("This is a responsive 1/3 width layout")


def render_content():
    section_title("Content")
    with gui.tag("div", className="container-fluid"), gui.tag("div", className="row"):
        # LEFT SIDE
        with gui.tag("div", className="col-12 col-md-6"):
            render_headings()
        # RIGHT SIDE
        with gui.tag("div", className="col-12 col-md-6"):
            sub_section_title("Normal Text")
            normal_text()

            sub_section_title("Link")
            link()

            sub_section_title("Colored Text")
            colored_text()


def render_headings():
    sub_section_title("Headings")
    render_h1_to_h6_headings()


@show_source_code
def render_h1_to_h6_headings():
    with gui.tag("h1"):
        gui.html("This is a h1 heading")
    with gui.tag("h2"):
        gui.html("This is a h2 heading")
    with gui.tag("h3"):
        gui.html("This is a h3 heading")
    with gui.tag("h4"):
        gui.html("This is a h4 heading")
    with gui.tag("h5"):
        gui.html("This is a h5 heading")
    with gui.tag("h6"):
        gui.html("This is a h6 heading")


@show_source_code
def normal_text():
    gui.write("This is a normal text")


@show_source_code
def link():
    with gui.tag("a", href="https://www.gooey.ai"):
        gui.html("This is a link")


@show_source_code
def colored_text():
    with gui.tag("p", className="text-primary"):
        gui.html("This is a primary text")
    with gui.tag("p", className="text-secondary"):
        gui.html("This is a secondary text")
    with gui.tag("p", className="text-success"):
        gui.html("This is a success text")
    with gui.tag("p", className="text-danger"):
        gui.html("This is a danger text")
    with gui.tag("p", className="text-warning"):
        gui.html("This is a warning text")
    with gui.tag("p", className="text-info"):
        gui.html("This is a info text")
    with gui.tag("p", className="text-light bg-dark"):
        gui.html("This is a light text")


def render_components():
    section_title("Components")
    with gui.tag("div", className="container-fluid"), gui.tag("div", className="row"):
        # LEFT SIDE
        with gui.tag("div", className="col-12 col-md-6"):
            # BUTTONS
            buttons_group()

            # TABS
            render_tabs_example()

        # RIGHT SIDE
        with gui.tag("div", className="col-12 col-md-6"):
            # ALERTS
            render_alerts()

        # Inputs
        render_inputs()

        section_title("File Upload Button")
        file_upload()


@show_source_code
def file_upload():
    gui.file_uploader(
        "**Upload Any File**",
        key="file_uploader_test0",
        help="Attach a video/audio/file to this.",
        optional=True,
        accept=["audio/*"],
    )


def render_inputs():
    section_title("Inputs")
    sub_section_title("Text Area")

    @show_source_code
    def text_area():
        gui.text_area(
            "Label: Take some input from user",
            "",
            100,
            "textArea_test0",
            "want help?",
            "You can also show a placeholder",
        )

    text_area()

    sub_section_title("Multi Select")

    @show_source_code
    def multi_select():
        gui.multiselect(
            "Label: Click below to select multiple options",
            ["Option 1", "Option 2", "Option 3", "Option 4"],
        )

    multi_select()


def render_alerts():
    section_title("Alerts")

    @show_source_code
    def success_alert():
        gui.success("Yay, this is done!")

    success_alert()

    @show_source_code
    def error_alert():
        gui.error("Oops, please try again!")

    error_alert()


def render_tabs_example():
    section_title("Tabs")
    # Rounded Tabs
    sub_section_title("Rounded Tabs")

    @show_source_code
    def rounded_tabs():
        tab1, tab2, tab3 = gui.tabs(["Tab 1", "Tab 2", "Tab 3"])
        with tab1:
            gui.write("This is tab 1 content")
        with tab2:
            gui.write("This is tab 2 content")
        with tab3:
            gui.write("This is tab 3 content")

    rounded_tabs()

    # Underline Tabs
    selected_tab = "Tab 1"
    sub_section_title("Underline Tabs")

    @show_source_code
    def underline_tabs():
        with gui.nav_tabs():
            for name in ["Tab 1", "Tab 2", "Tab 4"]:
                url = "/components"
                with gui.nav_item(url, active=name == selected_tab):
                    gui.html(name)
        with gui.nav_tab_content():
            if selected_tab == "Tab 1":
                gui.write("This is tab 1 content")
            elif selected_tab == "Tab 2":
                gui.write("This is tab 2 content")
            else:
                gui.write("This is tab 3 content")

    underline_tabs()


def buttons_group():
    sub_section_title("Buttons")
    buttons()


@show_source_code
def buttons():
    with gui.tag("div"), gui.tag("div", className="d-flex justify-content-around"):
        gui.button("Primary", key="test0", type="primary")
        gui.button("Secondary", key="test1")
        gui.button("Tertiary", key="test3", type="tertiary")
        gui.button("Link Button", key="test3", type="link")


def code_block(content: str):
    code_lines = content.split("\n")[1:]
    formatted_code = "\n".join(code_lines)
    with gui.tag("div", className="mt-4"):
        gui.write(
            rf"""
                ```python %s
            """
            % formatted_code,
            unsafe_allow_html=True,
        )


def section_title(title: str):
    with (
        gui.tag("div", className="mb-4 mt-4 bg-light border-1 p-2"),
        gui.tag("h3", style={"font-weight": "500", "margin": "0"}),
    ):
        gui.html(title.upper())


def sub_section_title(title: str):
    with gui.tag(
        "h4",
        className="text-muted mb-2",
    ):
        gui.html(title)


def heading(
    title: str, description: str, margin_top: str = "2rem", margin_bottom: str = "2rem"
):
    with gui.tag(
        "div", style={"margin-top": margin_top, "margin-bottom": margin_bottom}
    ):
        with gui.tag(
            "p",
            style={"margin-top": "0rem", "margin-bottom": "0rem"},
            className="text-muted",
        ):
            gui.html(description.upper())
        with gui.tag(
            "h1",
            style={"margin-top": "0px", "margin-bottom": "0px", "font-weight": "500"},
        ):
            gui.html(title)
