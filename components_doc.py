import gooey_ui as gui
from gooey_ui import state

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


def render_layouts():
    section_title("Layouts")
    sub_section_title("Full Width Layout")
    with gui.tag("div", className="container-fluid bg-light p-4"):
        with gui.tag("div", className="row"):
            with gui.tag("div", className="col-12"):
                gui.html("This is a full width layout")
    code_block(
        """
        with gui.tag("div", className="container-fluid bg-light p-4"):
            with gui.tag("div", className="row"):
                with gui.tag("div", className="col-12"):
                    gui.html("This is a full width layout")"""
    )
    sub_section_title("Full Width 1/2 Layout")
    with gui.tag("div", className="container-fluid p-2"):
        with gui.tag("div", className="row"):
            with gui.tag("div", className="col-6 border"):
                gui.html("This is a 1/2 width layout")
            with gui.tag("div", className="col-6 border"):
                gui.html("This is a 1/2 width layout")
    code_block(
        """with gui.tag("div", className="container-fluid p-4"):
                    with gui.tag("div", className="row"):
                        with gui.tag("div", className="col-6 border"):
                            gui.html("This is a 1/2 width layout")
                        with gui.tag("div", className="col-6 border"):
                            gui.html("This is a 1/2 width layout")"""
    )
    sub_section_title("Full Width 1/3 Layout")
    with gui.tag("div", className="container-fluid p-2"):
        with gui.tag("div", className="row"):
            with gui.tag("div", className="col-4 border"):
                gui.html("This is a 1/3 width layout")
            with gui.tag("div", className="col-4 border"):
                gui.html("This is a 1/3 width layout")
            with gui.tag("div", className="col-4 border"):
                gui.html("This is a 1/3 width layout")
    code_block(
        """with gui.tag("div", className="container-fluid p-2"):
                    with gui.tag("div", className="row"):
                        with gui.tag("div", className="col-4 border"):
                            gui.html("This is a 1/3 width layout")
                        with gui.tag("div", className="col-4 border"):
                            gui.html("This is a 1/3 width layout")
                        with gui.tag("div", className="col-4 border"):
                            gui.html("This is a 1/3 width layout")"""
    )
    sub_section_title("Responsive 1/3 Layout")
    gui.write("These columns will go full width on small devices")
    with gui.tag("div", className="container-fluid p-2"):
        with gui.tag("div", className="row"):
            with gui.tag("div", className="col-12 col-md-4 border"):
                gui.html("This is a responsive 1/3 width layout")
            with gui.tag("div", className="col-12 col-md-4 border"):
                gui.html("This is a responsive 1/3 width layout")
            with gui.tag("div", className="col-12 col-md-4 border"):
                gui.html("This is a responsive 1/3 width layout")
    code_block(
        """with gui.tag("div", className="container-fluid p-2"):
                    with gui.tag("div", className="row"):
                        with gui.tag("div", className="col-12 col-md-4 border"):
                            gui.html("This is a responsive 1/3 width layout")
                        with gui.tag("div", className="col-12 col-md-4 border"):
                            gui.html("This is a responsive 1/3 width layout")
                        with gui.tag("div", className="col-12 col-md-4 border"):
                            gui.html("This is a responsive 1/3 width layout")
                        """
    )


def render_content():
    section_title("Content")
    with gui.tag("div", className="container-fluid"):
        with gui.tag("div", className="row"):
            # LEFT SIDE
            with gui.tag("div", className="col-12 col-md-6"):
                render_headings()

            # RIGHT SIDE
            with gui.tag("div", className="col-12 col-md-6"):
                sub_section_title("Normal Text")
                gui.write("This is a normal text")
                code_block('gui.write("This is a normal text")')
                sub_section_title("Link")
                with gui.tag("a", href="https://www.gooey.ai"):
                    gui.html("This is a link")
                code_block(
                    """with gui.tag("a", href="https://www.gooey.ai"): 
                            gui.html("This is a link")"""
                )
                sub_section_title("Colored Text")
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
                code_block(
                    """with gui.tag("p", className="text-primary"):
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
                            gui.html("This is a light text")"""
                )


def render_components():
    section_title("Components")
    with gui.tag("div", className="container-fluid"):
        with gui.tag("div", className="row"):
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
            file = gui.file_uploader(
                "**Upload Any File**",
                key="file_uploader_test0",
                help="Attach a video/audio/file to this.",
                optional=True,
                accept=["audio/*"],
            )


def render_headings():
    sub_section_title("Headings")
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

    code_block(
        """
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
    """
    )


def render_inputs():
    section_title("Inputs")
    sub_section_title("Text Area")
    gui.text_area(
        "Label: Take some input from user",
        "",
        100,
        "textArea_test0",
        "want help?",
        "You can also show a placeholder",
    )
    code_block(
        'gui.text_area("Example Text Area","",100,"textAreat_test0","want help?","You can also show a placeholder")'
    )

    sub_section_title("Multi Select")
    gui.multiselect(
        "Label: Click below to select multiple options",
        ["Option 1", "Option 2", "Option 3", "Option 4"],
    )
    code_block(
        'gui.multiselect("Multi Select", ["Option 1", "Option 2", "Option 3", "Option 4"])'
    )


def render_alerts():
    section_title("Alerts")
    gui.success("Yay, this is done!")
    code_block('gui.success("Yay, this is done!")')

    gui.error("Opps, please try again!")
    code_block('gui.error("Opps, please try again!")')


def render_tabs_example():
    section_title("Tabs")
    # Rounded Tabs
    sub_section_title("Rounded Tabs")
    tab1, tab2, tab3 = gui.tabs(["Tab 1", "Tab 2", "Tab 3"])
    with tab1:
        gui.write("This is tab 1 content")
    with tab2:
        gui.write("This is tab 2 content")
    with tab3:
        gui.write("This is tab 3 content")

    code_block(
        """
    tab1, tab2, tab3 = gui.tabs(["Tab 1", "Tab 2", "Tab 3"])
    with tab1:
        gui.html("This is tab 1 content")
    with tab2:
        gui.html("This is tab 2 content")
    with tab3:
        gui.html("This is tab 3 content")
    """
    )

    # Underline Tabs
    selected_tab = "Tab 1"
    sub_section_title("Underline Tabs")
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

    code_block(
        """
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
    """
    )


def buttons_group():
    sub_section_title("Buttons")
    with gui.tag("div"):
        with gui.tag("div", className="d-flex justify-content-around"):
            gui.button("Primary", key="test0", type="primary")
            gui.button("Secondary", key="test1")
            gui.button("Tertiary", key="test3", type="tertiary")
            gui.button("Link Button", key="test3", type="link")

        code_block('gui.button("Primary", key="test0", type="primary")')
        code_block('gui.button("Secondary", key="test1")')
        code_block('gui.button("Tertiary", key="test3", type="tertiary")')
        code_block('gui.button("Link Button", key="test3", type="link")')


def code_block(content: str):
    with gui.tag("div", className="mt-4"):
        gui.write(
            rf"""
                ```python
                %s
            """
            % content,
            unsafe_allow_html=True,
        )


def collapsible_section(title: str) -> state.NestingCtx:
    with gui.expander(title):
        return state.NestingCtx()


def section_title(title: str):
    with gui.tag("div", className="mb-4 mt-4 bg-light border-1 p-2"):
        with gui.tag("h3", style={"font-weight": "500", "margin": "0"}):
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
