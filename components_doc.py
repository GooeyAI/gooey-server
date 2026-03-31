import inspect
from functools import wraps

import gooey_gui as gui

META_TITLE = "Gooey Component Library"
META_DESCRIPTION = "Interactive reference for all gooey-gui components"

TITLE = "Component Library"
DESCRIPTION = "gooey-gui"

SECTIONS = [
    ("layouts", "Layouts"),
    ("content", "Content & Text"),
    ("icons", "Icons"),
    ("navigation", "Navigation"),
    ("inputs-text", "Text Inputs"),
    ("inputs-numeric", "Numeric & Date"),
    ("inputs-selection", "Selection"),
    ("inputs-file", "File Upload"),
    ("buttons", "Buttons & Links"),
    ("media", "Media"),
    ("overlays", "Overlays"),
    ("data", "Data Display"),
    ("styling", "Styling & Scripting"),
    ("state", "State"),
]


def render():
    with gui.div(className="container-fluid px-3 px-md-5 py-4"):
        render_layouts()
        render_content_and_text()
        render_icons()
        render_navigation()
        render_inputs_text()
        render_inputs_numeric()
        render_inputs_selection()
        render_inputs_file()
        render_buttons_and_links()
        render_media()
        render_overlays()
        render_data_display()
        render_styling_and_scripting()
        render_state()


# ╔══════════════════════════════════════════════════════════════╗
# ║  Helpers: source-code toggle, section chrome                ║
# ╚══════════════════════════════════════════════════════════════╝


def show_source(fn):
    """Decorator that renders the component, then shows source in a collapsible expander."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        out = fn(*args, **kwargs)
        # strip the decorator line + def indentation for cleaner display
        src_lines = inspect.getsource(fn).split("\n")
        # skip the @show_source decorator line
        src_lines = [
            line for line in src_lines if not line.strip().startswith("@show_source")
        ]
        formatted = "\n".join(src_lines)
        with (
            gui.div(className="my-3"),
            gui.expander("**View source**", key=f"src_{fn.__name__}"),
        ):
            gui.write(f"```python\n{formatted}\n```", unsafe_allow_html=True)
        return out

    return wrapper


SIDEBAR_KEY = "components-sidebar"


def render_sidebar_nav():
    """Render header and navigation links in the sidebar."""
    close_js = f"window.dispatchEvent(new Event('{SIDEBAR_KEY}:close'))"

    with gui.div(
        className="p-3 border-bottom d-flex justify-content-between align-items-start bg-white"
    ):
        with gui.div():
            # inline github link
            with gui.tag(
                "a",
                href="https://github.com/GooeyAI/gooey-gui",
                className="text-decoration-none text-muted",
            ):
                gui.html(f"{DESCRIPTION} <i class='fa-brands fa-github'></i>")

            gui.write(f"### {TITLE}", className="d-block")
        with gui.tag(
            "button",
            className="d-block d-lg-none btn btn-sm btn-outline-secondary border-0",
            onClick=close_js,
        ):
            gui.html('<i class="fa-solid fa-xmark"></i>')

    with gui.div(className="p-3 d-flex flex-column gap-1"):
        for anchor_id, label in SECTIONS:
            with gui.tag(
                "a",
                href=f"#section-{anchor_id}",
                className="btn btn-sm btn-outline-secondary text-start border-0 py-1 px-2",
                onClick=f"if(window.innerWidth < 1140) {{ {close_js} }}",
            ):
                gui.html(label)


def _section(section_id: str, title: str, subtitle: str = ""):
    """Section header with anchor target."""
    with gui.div(
        id=f"section-{section_id}",
        className="mt-4 mb-3 pt-2 border-bottom border-dark border-2 pb-2",
    ):
        with gui.tag("h2", className="fw-bold fs-4 mb-0"):
            gui.html(title)
        if subtitle:
            with gui.tag("p", className="text-muted small mb-0 mt-1"):
                gui.html(subtitle)


class _card_ctx:
    """Context manager for a demo card with a title."""

    def __init__(self, title: str = ""):
        self.title = title

    def __enter__(self):
        self._div = gui.div(className="bg-white border rounded-3 p-3 mb-3")
        self._div.__enter__()
        if self.title:
            gui.write(f"**{self.title}**")
        return self

    def __exit__(self, *args):
        self._div.__exit__(*args)


# ╔══════════════════════════════════════════════════════════════╗
# ║  1. Styling & Scripting                                     ║
# ╚══════════════════════════════════════════════════════════════╝


def render_styling_and_scripting():
    _section(
        "styling",
        "Styling & Scripting",
        "gui.styled, gui.js, and Bootstrap 5 className",
    )

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.styled — Scoped CSS with & selector"):
            demo_styled()

    with col2:
        with _card_ctx("Bootstrap 5 className"):
            demo_bootstrap_classes()

    with _card_ctx("gui.js — Inject JavaScript"):
        demo_js()


@show_source
def demo_styled():
    """gui.styled scopes CSS to its container using & as the selector."""
    with gui.styled(
        """
        & {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-radius: 12px;
            padding: 1.5rem;
            color: white;
        }
        & strong { color: #ffd700; }
    """
    ):
        gui.html(
            "This container has <strong>scoped gradient styles</strong> via <code>gui.styled()</code>"
        )


@show_source
def demo_bootstrap_classes():
    """Use Bootstrap 5 utility classes via className on any component."""
    with gui.div(className="d-flex flex-column gap-2"):
        with gui.div(className="p-3 bg-dark text-white rounded"):
            gui.html("bg-dark + text-white + rounded")
        with gui.div(className="p-3 border border-2 border-primary rounded"):
            gui.html("border-primary")
        with gui.div(className="p-3 bg-light text-center fw-bold shadow-sm rounded"):
            gui.html("bg-light + shadow-sm + fw-bold")


@show_source
def demo_js():
    """Inject a script tag. Useful for loading external widgets."""
    gui.write(
        "`gui.js(src, **kwargs)` injects a `<script>` tag. "
        "Used internally to load GooeyEmbed and other JS widgets."
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  Icons — Font Awesome                                        ║
# ╚══════════════════════════════════════════════════════════════╝


def render_icons():
    _section(
        "icons",
        "Icons",
        "Font Awesome 6 — use <i> tags with gui.html()",
    )

    with _card_ctx("How to render icons"):
        demo_icons_usage()

    with _card_ctx("Common icon styles"):
        demo_icon_styles()

    with _card_ctx("Icons in buttons"):
        demo_icons_in_buttons()


@show_source
def demo_icons_usage():
    """Render icons using Font Awesome <i> tags inside gui.html()."""
    with gui.div(className="d-flex gap-4 align-items-center fs-4"):
        gui.html('<i class="fa-solid fa-house"></i>')
        gui.html('<i class="fa-solid fa-gear"></i>')
        gui.html('<i class="fa-solid fa-bell"></i>')
        gui.html('<i class="fa-solid fa-user"></i>')
        gui.html('<i class="fa-solid fa-magnifying-glass"></i>')
        gui.html('<i class="fa-regular fa-heart"></i>')
        gui.html('<i class="fa-regular fa-envelope"></i>')
        gui.html('<i class="fa-solid fa-check"></i>')


@show_source
def demo_icon_styles():
    """Size, color, and animation classes on icons."""
    with gui.div(className="d-flex gap-4 align-items-center"):
        # Sizes
        gui.html('<i class="fa-solid fa-star fa-xs"></i>')
        gui.html('<i class="fa-solid fa-star fa-sm"></i>')
        gui.html('<i class="fa-solid fa-star"></i>')
        gui.html('<i class="fa-solid fa-star fa-lg"></i>')
        gui.html('<i class="fa-solid fa-star fa-xl"></i>')
        gui.html('<i class="fa-solid fa-star fa-2xl"></i>')
    gui.newline()
    with gui.div(className="d-flex gap-4 align-items-center fs-4"):
        # Colors via Bootstrap text utilities
        gui.html('<i class="fa-solid fa-circle-check text-success"></i>')
        gui.html('<i class="fa-solid fa-triangle-exclamation text-warning"></i>')
        gui.html('<i class="fa-solid fa-circle-xmark text-danger"></i>')
        gui.html('<i class="fa-solid fa-circle-info text-primary"></i>')
    gui.newline()
    with gui.div(className="d-flex gap-4 align-items-center fs-4"):
        # Spinner / animation
        gui.html('<i class="fa-solid fa-spinner fa-spin"></i>')
        gui.html('<i class="fa-solid fa-rotate fa-spin"></i>')


@show_source
def demo_icons_in_buttons():
    """Combine icons with text in buttons using gui.button or gui.anchor."""
    with gui.div(className="d-flex gap-2 flex-wrap"):
        gui.button(
            '<i class="fa-solid fa-plus"></i> Create',
            key="demo_icon_btn_create",
            type="primary",
        )
        gui.button(
            '<i class="fa-solid fa-trash"></i> Delete',
            key="demo_icon_btn_delete",
            type="tertiary",
        )
        gui.button(
            '<i class="fa-regular fa-download"></i> Download',
            key="demo_icon_btn_download",
        )
        gui.anchor(
            '<i class="fa-solid fa-arrow-up-right-from-square"></i> Open link',
            href="https://fontawesome.com/search",
            type="link",
            new_tab=True,
            unsafe_allow_html=True,
        )


# ╔══════════════════════════════════════════════════════════════╗
# ║  2. Layouts                                                  ║
# ╚══════════════════════════════════════════════════════════════╝


def render_layouts():
    _section(
        "layouts",
        "Layouts",
        "gui.div, gui.tag, gui.columns, gui.center, gui.expander, sidebar_layout",
    )

    with _card_ctx("gui.columns — Equal columns"):
        demo_columns_equal()

    with _card_ctx("gui.columns — Weighted columns"):
        demo_columns_weighted()

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.center"):
            demo_center()
    with col2:
        with _card_ctx("gui.expander"):
            demo_expander()

    with _card_ctx("gui.div & gui.tag"):
        demo_div_and_tag()

    with _card_ctx("sidebar_layout — Collapsible sidebar"):
        demo_sidebar()


@show_source
def demo_columns_equal():
    """Two equal columns (responsive by default — stack on mobile)."""
    col1, col2 = gui.columns(2)
    with col1:
        with gui.div(className="bg-light p-3 rounded text-center"):
            gui.html("Column 1")
    with col2:
        with gui.div(className="bg-light p-3 rounded text-center"):
            gui.html("Column 2")


@show_source
def demo_columns_weighted():
    """Weighted columns: pass a list of proportions."""
    col_narrow, col_wide = gui.columns([1, 3])
    with col_narrow:
        with gui.div(className="bg-dark text-white p-3 rounded text-center"):
            gui.html("1/4")
    with col_wide:
        with gui.div(className="bg-light p-3 rounded text-center"):
            gui.html("3/4")


@show_source
def demo_center():
    """Centers children using flexbox."""
    with gui.center(className="bg-light rounded p-4"):
        gui.write("Centered content")
        gui.caption("Both horizontally and vertically")


@show_source
def demo_expander():
    """Collapsible section."""
    with gui.expander("Click to expand", key="demo_expander_1"):
        gui.write("Hidden content revealed!")
        gui.caption("Use for optional details, advanced settings, etc.")


@show_source
def demo_div_and_tag():
    """gui.div(**props) is shorthand for gui.tag('div', **props)."""
    with gui.div(className="d-flex gap-2"):
        with gui.tag("span", className="badge bg-primary"):
            gui.html("gui.tag('span')")
        with gui.tag("span", className="badge bg-secondary"):
            gui.html("any HTML tag")
        with gui.tag("em"):
            gui.html("even inline elements")


@show_source
def demo_sidebar():
    """sidebar_layout returns (sidebar, page_content) context managers. Open/close via JS events."""
    gui.write("This page itself uses `sidebar_layout` for the left navigation panel.")
    gui.newline()
    gui.write("**Pattern used on this page:**")
    gui.write(
        "```python\n"
        "from widgets.sidebar import sidebar_layout\n"
        "\n"
        "# In your route handler:\n"
        "sidebar, page_content = sidebar_layout(\n"
        '    key="my-sidebar",\n'
        "    session=request.session,\n"
        ")\n"
        "\n"
        "with sidebar:\n"
        "    # Sidebar content — nav links, filters, etc.\n"
        '    gui.write("**Navigation**")\n'
        "    for section in sections:\n"
        '        with gui.tag("a", href=f"#section-{section.id}"):\n'
        "            gui.html(section.label)\n"
        "\n"
        "with page_content:\n"
        "    # Main page content\n"
        "    render_page()\n"
        "```",
        unsafe_allow_html=True,
    )
    gui.newline()
    gui.write("**Open / close via JavaScript events:**")
    gui.write(
        "```javascript\n"
        "// Open the sidebar\n"
        "window.dispatchEvent(new Event('my-sidebar:open'))\n"
        "\n"
        "// Close the sidebar\n"
        "window.dispatchEvent(new Event('my-sidebar:close'))\n"
        "```",
        unsafe_allow_html=True,
    )
    gui.newline()
    open_js = f"window.dispatchEvent(new Event('{SIDEBAR_KEY}:open'))"
    close_js = f"window.dispatchEvent(new Event('{SIDEBAR_KEY}:close'))"
    gui.write("**Try it:**")
    with gui.div(className="d-flex gap-2"):
        with gui.tag("button", className="btn btn-sm btn-primary", onClick=open_js):
            gui.html('<i class="fa-solid fa-bars"></i> Open sidebar')
        with gui.tag(
            "button", className="btn btn-sm btn-outline-secondary", onClick=close_js
        ):
            gui.html('<i class="fa-solid fa-xmark"></i> Close sidebar')


# ╔══════════════════════════════════════════════════════════════╗
# ║  3. Content & Text                                          ║
# ╚══════════════════════════════════════════════════════════════╝


def render_content_and_text():
    _section(
        "content",
        "Content & Text",
        "gui.write, gui.markdown, gui.text, gui.html, gui.caption, gui.error, gui.success",
    )

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.write — Primary output (supports Markdown)"):
            demo_write()

        with _card_ctx("gui.html — Raw HTML"):
            demo_html()

        with _card_ctx("gui.error & gui.success"):
            demo_alerts()

    with col2:
        with _card_ctx("gui.markdown — Explicit Markdown block"):
            demo_markdown()

        with _card_ctx("gui.text — Preformatted text"):
            demo_text()

        with _card_ctx("gui.caption & gui.newline"):
            demo_caption_newline()

    with _card_ctx("Headings via gui.write"):
        demo_headings()


@show_source
def demo_write():
    """gui.write renders markdown, objects, or plain strings."""
    gui.write("**Bold**, *italic*, and `inline code`")
    gui.write("With help tooltip", help="This appears on hover")


@show_source
def demo_markdown():
    """gui.markdown renders an explicit markdown block."""
    gui.markdown(
        "### Markdown heading\n\n- List item one\n- List item two\n\n> Blockquote text"
    )


@show_source
def demo_text():
    """gui.text renders preformatted text (like <pre>)."""
    gui.text(
        "This is preformatted text.\n  Indentation is preserved.\n    Like a <pre> block."
    )


@show_source
def demo_html():
    """gui.html renders raw HTML content."""
    gui.html(
        '<span style="color: #e74c3c; font-weight: bold;">Raw HTML</span> with inline styles'
    )


@show_source
def demo_caption_newline():
    """gui.caption for small muted text, gui.newline for line breaks."""
    gui.write("Regular text above")
    gui.caption("This is a caption — small and muted")
    gui.newline()
    gui.caption("After a gui.newline() break")


@show_source
def demo_alerts():
    """Status messages with icons."""
    gui.success("Operation completed successfully!")
    gui.error("Something went wrong, please try again.")


@show_source
def demo_headings():
    """Heading levels via gui.write markdown."""
    col1, col2 = gui.columns(2, responsive=False)
    with col1:
        gui.write("# Heading 1")
        gui.write("## Heading 2")
        gui.write("### Heading 3")
    with col2:
        gui.write("#### Heading 4")
        gui.write("##### Heading 5")
        gui.write("###### Heading 6")


# ╔══════════════════════════════════════════════════════════════╗
# ║  4. Navigation                                              ║
# ╚══════════════════════════════════════════════════════════════╝


def render_navigation():
    _section(
        "navigation",
        "Navigation",
        "gui.tabs, gui.controllable_tabs, gui.nav_tabs, gui.breadcrumbs",
    )

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.tabs — Rounded tabs"):
            demo_tabs()

        with _card_ctx("gui.breadcrumbs"):
            demo_breadcrumbs()

    with col2:
        with _card_ctx("gui.nav_tabs — Underline tabs"):
            demo_nav_tabs()

        with _card_ctx("gui.controllable_tabs"):
            demo_controllable_tabs()


@show_source
def demo_tabs():
    """Simple tabbed layout. Returns a list of context managers."""
    tab1, tab2, tab3 = gui.tabs(["Overview", "Details", "Settings"])
    with tab1:
        gui.write("Overview content here")
    with tab2:
        gui.write("Details content here")
    with tab3:
        gui.write("Settings content here")


@show_source
def demo_nav_tabs():
    """Underline-style navigation tabs."""
    with gui.nav_tabs():
        for name in ["Active", "Inactive 1", "Inactive 2"]:
            with gui.nav_item("/GuiComponents/", active=name == "Active"):
                gui.html(name)
    with gui.nav_tab_content():
        gui.write("Content for the active tab")


@show_source
def demo_controllable_tabs():
    """Tabs with programmatic control via session state key."""
    tabs, index = gui.controllable_tabs(
        ["First", "Second", "Third"], key="demo_ctrl_tabs"
    )
    with tabs[index]:
        gui.write(f"Selected tab index: **{index}**")


@show_source
def demo_breadcrumbs():
    """Breadcrumb navigation with custom divider."""
    with gui.breadcrumbs(divider=">"):
        gui.breadcrumb_item("Home", link_to="/")
        gui.breadcrumb_item("Components", link_to="/GuiComponents/")
        gui.breadcrumb_item("Navigation")


# ╔══════════════════════════════════════════════════════════════╗
# ║  5. Inputs — Text                                          ║
# ╚══════════════════════════════════════════════════════════════╝


def render_inputs_text():
    _section(
        "inputs-text",
        "Text Inputs",
        "gui.text_input, gui.text_area, gui.password_input, gui.code_editor",
    )

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.text_input"):
            demo_text_input()

        with _card_ctx("gui.text_area"):
            demo_text_area()

    with col2:
        with _card_ctx("gui.password_input"):
            demo_password_input()

        with _card_ctx("gui.code_editor"):
            demo_code_editor()


@show_source
def demo_text_input():
    """Single-line text input."""
    gui.text_input(
        "Your name",
        key="demo_text_input",
        placeholder="Enter your name",
        help="This is a help tooltip",
    )


@show_source
def demo_text_area():
    """Multi-line text area with configurable height."""
    gui.text_area(
        "Description",
        key="demo_text_area",
        height=100,
        placeholder="Write something here...",
        help="Supports multi-line input",
    )


@show_source
def demo_password_input():
    """Password field — input is masked."""
    gui.password_input(
        "API Key",
        key="demo_password_input",
        placeholder="sk-...",
    )


@show_source
def demo_code_editor():
    """Code editor with syntax highlighting."""
    gui.code_editor(
        value='def hello():\n    print("Hello, Gooey!")',
        key="demo_code_editor",
        label="Python snippet",
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  6. Inputs — Numeric & Date                                ║
# ╚══════════════════════════════════════════════════════════════╝


def render_inputs_numeric():
    _section(
        "inputs-numeric",
        "Numeric & Date Inputs",
        "gui.number_input, gui.slider, gui.date_input",
    )

    col1, col2, col3 = gui.columns(3)
    with col1:
        with _card_ctx("gui.number_input"):
            demo_number_input()

    with col2:
        with _card_ctx("gui.slider"):
            demo_slider()

    with col3:
        with _card_ctx("gui.date_input"):
            demo_date_input()


@show_source
def demo_number_input():
    """Numeric input with min/max/step."""
    gui.number_input(
        "Temperature",
        min_value=0.0,
        max_value=2.0,
        value=0.7,
        step=0.1,
        key="demo_number_input",
    )


@show_source
def demo_slider():
    """Range slider."""
    gui.slider(
        "Volume",
        min_value=0,
        max_value=100,
        value=50,
        key="demo_slider",
    )


@show_source
def demo_date_input():
    """Date picker input."""
    gui.date_input(
        "Start date",
        key="demo_date_input",
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  7. Inputs — Selection                                     ║
# ╚══════════════════════════════════════════════════════════════╝


def render_inputs_selection():
    _section(
        "inputs-selection",
        "Selection Inputs",
        "gui.checkbox, gui.switch, gui.radio, gui.horizontal_radio, gui.selectbox, gui.multiselect",
    )

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.checkbox"):
            demo_checkbox()

        with _card_ctx("gui.radio"):
            demo_radio()

        with _card_ctx("gui.selectbox"):
            demo_selectbox()

    with col2:
        with _card_ctx("gui.switch"):
            demo_switch()

        with _card_ctx("gui.horizontal_radio"):
            demo_horizontal_radio()

        with _card_ctx("gui.multiselect"):
            demo_multiselect()


@show_source
def demo_checkbox():
    """Boolean checkbox input."""
    gui.checkbox("Enable notifications", key="demo_checkbox", help="Toggle me")


@show_source
def demo_switch():
    """Toggle switch — an alternative to checkbox."""
    gui.switch("Dark mode", key="demo_switch")
    gui.switch("Small switch", key="demo_switch_sm", size="small")


@show_source
def demo_radio():
    """Vertical radio button group."""
    gui.radio(
        "Choose a model",
        options=["GPT-4o", "Claude", "Gemini"],
        key="demo_radio",
    )


@show_source
def demo_horizontal_radio():
    """Inline radio buttons rendered as toggle buttons."""
    gui.horizontal_radio(
        "Output format",
        options=["JSON", "CSV", "XML"],
        key="demo_horizontal_radio",
    )


@show_source
def demo_selectbox():
    """Single-select dropdown."""
    gui.selectbox(
        "Language",
        options=["Python", "JavaScript", "Go", "Rust"],
        key="demo_selectbox",
    )


@show_source
def demo_multiselect():
    """Multi-select dropdown."""
    gui.multiselect(
        "Tags",
        options=["AI", "ML", "NLP", "Vision", "Audio"],
        key="demo_multiselect",
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  8. Inputs — File Upload                                    ║
# ╚══════════════════════════════════════════════════════════════╝


def render_inputs_file():
    _section("inputs-file", "File Upload", "gui.file_uploader")

    with _card_ctx("gui.file_uploader"):
        demo_file_uploader()


@show_source
def demo_file_uploader():
    """File upload with accept filter."""
    gui.file_uploader(
        "**Upload a file**",
        key="demo_file_uploader",
        help="Attach any file",
        accept=["image/*", "audio/*", ".pdf"],
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  9. Buttons & Links                                         ║
# ╚══════════════════════════════════════════════════════════════╝


def render_buttons_and_links():
    _section(
        "buttons",
        "Buttons & Links",
        "gui.button, gui.anchor, gui.url_button, gui.download_button",
    )

    with _card_ctx("gui.button — All types"):
        demo_buttons()

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.anchor — Styled link"):
            demo_anchor()

    with col2:
        with _card_ctx("gui.url_button"):
            demo_url_button()

    with _card_ctx("gui.download_button"):
        demo_download_button()


@show_source
def demo_buttons():
    """Button variants: primary, secondary, tertiary, link."""
    with gui.div(className="d-flex gap-2 flex-wrap align-items-center"):
        gui.button("Primary", key="demo_btn_primary", type="primary")
        gui.button("Secondary", key="demo_btn_secondary")
        gui.button("Tertiary", key="demo_btn_tertiary", type="tertiary")
        gui.button("Link", key="demo_btn_link", type="link")
        gui.button("Disabled", key="demo_btn_disabled", disabled=True)


@show_source
def demo_anchor():
    """Styled anchor tag that looks like a button."""
    gui.anchor("Visit Gooey.AI", href="https://gooey.ai", type="primary", new_tab=True)


@show_source
def demo_url_button():
    """Quick external link button with icon."""
    gui.url_button("https://gooey.ai")


@show_source
def demo_download_button():
    """Triggers a file download."""
    gui.write(
        "`gui.download_button(label, url)` — renders a download link styled as a button."
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  10. Media                                                  ║
# ╚══════════════════════════════════════════════════════════════╝


def render_media():
    _section("media", "Media", "gui.image, gui.video, gui.audio")

    col1, col2, col3 = gui.columns(3)
    with col1:
        with _card_ctx("gui.image"):
            demo_image()

    with col2:
        with _card_ctx("gui.video"):
            demo_video()

    with col3:
        with _card_ctx("gui.audio"):
            demo_audio()


@show_source
def demo_image():
    """Image with caption and optional download button."""
    gui.image(
        "https://picsum.photos/400/200",
        caption="Random image via picsum.photos",
    )


@show_source
def demo_video():
    """Video player with optional autoplay."""
    gui.video(
        "https://v3b.fal.media/files/b/0a93710f/vY5DN0btTCiU7a5_yNqQf_0b3FO6JS.mp4#t=0.001",
        caption="🎥 Random video via YouTube",
        autoplay=True,
    )


@show_source
def demo_audio():
    """Audio player with optional download."""
    gui.audio(
        "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/0e7f71fc-dcd8-11ed-b644-02420a00015f/gooey.ai%20-%20four%20to%20the%20floor%20kick%20drum%20beat%20with...rhythms%20at%20a%20time%20signature%20of%2034%20andtempoof80%201.wav",
        caption="🎧 Random audio",
        show_download_button=True,
    )


def render_overlays():
    _section(
        "overlays",
        "Overlays & Feedback",
        "gui.tooltip, gui.popover, gui.pill, gui.modal_scaffold, gui.alert_dialog, gui.confirm_dialog",
    )

    col1, col2, col3 = gui.columns(3)
    with col1:
        with _card_ctx("gui.tooltip"):
            demo_tooltip()

    with col2:
        with _card_ctx("gui.popover"):
            demo_popover()

    with col3:
        with _card_ctx("gui.pill"):
            demo_pill()

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.alert_dialog"):
            demo_alert_dialog()

    with col2:
        with _card_ctx("gui.button_with_confirm_dialog"):
            demo_confirm_dialog()


@show_source
def demo_tooltip():
    """Wrap any element in gui.tooltip for a hover tooltip."""
    with gui.tooltip("I'm a tooltip!"):
        gui.button("Hover me", key="demo_tooltip_btn")


@show_source
def demo_popover():
    """Popover with custom content."""
    trigger, content = gui.popover()
    with trigger:
        gui.button("Open popover", key="demo_popover_btn")
    with content:
        gui.write("**Popover content**")
        gui.caption("Any gui components can go here")


@show_source
def demo_pill():
    """Badge / pill component."""
    with gui.div(className="d-flex gap-2 flex-wrap"):
        gui.pill("Default")
        gui.pill("Primary", text_bg="primary")
        gui.pill("Secondary", text_bg="secondary")
        gui.pill("Dark", text_bg="dark")


@show_source
def demo_alert_dialog():
    """Modal alert dialog with open/close state."""
    ref = gui.use_alert_dialog("demo_alert")
    if gui.button("Open alert", key="demo_alert_open", type="primary"):
        ref.set_open(True)
    if ref.is_open:
        with gui.alert_dialog(ref, "Alert Title"):
            gui.write("This is an alert dialog. Click ✕ to close.")


@show_source
def demo_confirm_dialog():
    """Confirm dialog with built-in trigger button."""
    ref = gui.use_confirm_dialog("demo_confirm")
    with gui.button_with_confirm_dialog(
        ref=ref,
        trigger_label="Delete item",
        trigger_type="primary",
        modal_title="Are you sure?",
        modal_content="This action cannot be undone.",
        confirm_label="Delete",
        confirm_className="btn-danger",
    ):
        pass
    if ref.pressed_confirm:
        gui.success("Item deleted!")


# ╔══════════════════════════════════════════════════════════════╗
# ║  12. Data Display                                           ║
# ╚══════════════════════════════════════════════════════════════╝


def render_data_display():
    _section(
        "data", "Data Display", "gui.table, gui.data_table, gui.json, gui.plotly_chart"
    )

    col1, col2 = gui.columns(2)
    with col1:
        with _card_ctx("gui.json — Interactive JSON viewer"):
            demo_json()

    with col2:
        with _card_ctx("gui.data_table"):
            demo_data_table()

    with _card_ctx("gui.plotly_chart"):
        demo_plotly_chart()


@show_source
def demo_json():
    """Interactive, collapsible JSON viewer."""
    gui.json(
        {
            "name": "Gooey.AI",
            "components": 45,
            "features": ["server-driven UI", "Bootstrap 5", "realtime updates"],
            "nested": {"key": "value", "list": [1, 2, 3]},
        },
        expanded=True,
    )


@show_source
def demo_data_table():
    """Data table from a list of cell values."""
    gui.data_table(
        [
            ["Component", "Category", "Status"],
            ["gui.button", "Buttons", "Stable"],
            ["gui.switch", "Inputs", "Stable"],
            ["gui.styled", "Styling", "Stable"],
        ]
    )


@show_source
def demo_plotly_chart():
    """Render a Plotly chart from a figure dict."""
    gui.write(
        "`gui.plotly_chart(figure_or_data)` — pass a Plotly figure object or dict.\n\n"
        "Requires plotly to be installed."
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║  13. State                                                  ║
# ╚══════════════════════════════════════════════════════════════╝


def render_state():
    _section("state", "State Management", "gui.session_state")

    with _card_ctx("gui.session_state — Per-user state dict"):
        demo_session_state()


@show_source
def demo_session_state():
    """Dict-like object for reading/writing per-user state. All input components store their values here."""
    gui.write(
        "All input components automatically read from and write to `gui.session_state`.\n\n"
        "```python\n"
        "# Read a value\n"
        "name = gui.session_state.get('user_name', 'default')\n\n"
        "# Write a value\n"
        "gui.session_state['user_name'] = 'Alice'\n\n"
        "# Use with inputs — the key links the widget to state\n"
        "gui.text_input('Name', key='user_name')\n"
        "```"
    )
