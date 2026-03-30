---
name: gooey-gui
description: Use when writing UI code in gooey-server Python files — building pages, forms, layouts, or any visual component using the gooey-gui library. Use when importing gooey_gui, calling gui.write, gui.div, gui.button, gui.columns, gui.styled, or any gui.* component. Use when styling with Bootstrap 5 classes in gooey-server.
user-invocable: true
disable-model-invocation: false
---

# gooey-gui — Server-Driven UI Component Library

## Overview

gooey-gui is a **server-driven UI library** where Python code on the server builds a JSON component tree that a React/Remix frontend renders. There is no client-side Python — every `gui.*` call appends a node to a render tree that gets serialized to JSON and sent to the browser.

**Core mental model:** Think of it like writing HTML with Python context managers. Each `gui.*` call = one React component in the tree. Nesting = parent/child in the tree.

```python
import gooey_gui as gui

# Every gui.* call adds a node to the render tree
gui.write("Hello")                    # adds a markdown node
with gui.div(className="p-3"):       # adds a div node, children nested inside
    gui.button("Click me", key="btn") # adds a button node as child of div
```

## Critical Rules

### 1. ALWAYS use Bootstrap 5 classes for styling

`className` prop is available on **every** component. Use Bootstrap 5 utility classes as the primary styling mechanism.

```python
# CORRECT — Bootstrap classes
with gui.div(className="d-flex gap-3 align-items-center p-3 bg-light rounded"):
    gui.write("Styled with Bootstrap")

# WRONG — inline style dict
with gui.div(style=dict(display="flex", gap="12px", padding="12px")):
    gui.write("Don't do this")
```

Common Bootstrap patterns:
- **Spacing:** `mt-2`, `mb-3`, `px-4`, `py-2`, `gap-3`
- **Flex:** `d-flex`, `flex-column`, `align-items-center`, `justify-content-between`, `flex-wrap`
- **Width:** `w-100`, `w-50`, `w-auto`
- **Text:** `fw-bold`, `text-muted`, `fs-5`, `text-center`, `text-start`
- **Colors:** `text-danger`, `text-success`, `bg-light`, `bg-dark`, `text-white`
- **Borders:** `border`, `rounded`, `rounded-3`, `border-primary`, `shadow-sm`
- **Display:** `d-none`, `d-md-block`, `d-flex`, `d-md-none`
- **Buttons (via className):** `btn-sm`, `w-100`, `text-start`

### 2. When to use gui.styled (and when NOT to)

`gui.styled(css)` creates a **scoped CSS context** where `&` is replaced with a generated unique class.

**USE gui.styled for:**
- Hover/focus/transition effects (Bootstrap can't do these)
- Complex selectors targeting children (`& a`, `& h2`)
- Animations and keyframes
- CSS properties Bootstrap doesn't cover (gradients, custom transforms)
- Pseudo-elements (`&::before`, `&::after`)

**DO NOT use gui.styled for:**
- Spacing, flex, colors, borders, typography — use Bootstrap classes
- One-off simple styles — use `style=dict(...)` prop if no Bootstrap class exists
- Anything Bootstrap 5 already has a utility class for

```python
# CORRECT — gui.styled for hover effect (Bootstrap can't do this)
with gui.styled("""
    & a:hover { background: #e9ecef; }
"""):
    with gui.tag("a", href="/page", className="d-block p-2 rounded text-decoration-none"):
        gui.html("Hoverable link")

# WRONG — gui.styled for basic spacing
with gui.styled("""
    & { padding: 1rem; margin-bottom: 0.5rem; }
"""):
    gui.write("Just use className='p-3 mb-2' instead")
```

### 3. Icons — Font Awesome 6 via `<i>` tags

Font Awesome is globally loaded. Render icons with `gui.html()`:

```python
# Inline icon
gui.html('<i class="fa-solid fa-check"></i>')

# Icon with Bootstrap color
gui.html('<i class="fa-solid fa-circle-check text-success fs-4"></i>')

# Icon in a button
gui.button('<i class="fa-solid fa-plus"></i> Create', key="create_btn", type="primary")

# Icon sizes: fa-xs, fa-sm, fa-lg, fa-xl, fa-2xl
# Styles: fa-solid, fa-regular, fa-light, fa-brands
# Animation: fa-spin, fa-bounce, fa-fade
```

### 4. gui.html vs gui.write — HTML escaping

- **`gui.write()`** — escapes HTML by default (safe for user content). Renders Markdown.
- **`gui.html()`** — renders raw HTML (for icons, custom markup). No Markdown.
- **`gui.write(..., unsafe_allow_html=True)`** — renders Markdown AND allows HTML.

```python
gui.write("**Bold markdown** with `code`")           # Markdown rendered, HTML escaped
gui.html('<i class="fa-solid fa-star"></i> Raw HTML') # HTML rendered directly
gui.write("# Title", unsafe_allow_html=True)          # Both markdown AND HTML
```

**Gotcha:** `gui.write` inside `gui.styled` can conflict — the `gui-md-container` class may override your scoped colors. Use `gui.html()` for styled containers with custom colors.

### 5. Context managers — nesting = parent/child

Most layout components are context managers. Nesting them creates a parent-child tree:

```python
with gui.div(className="card"):           # parent div
    with gui.div(className="card-body"):   # child div
        gui.write("Card content")          # grandchild text node
```

Components that return `NestingCtx` (use with `with`):
`div`, `tag`, `styled`, `center`, `expander`, `link`, `columns` (each col), `tabs` (each tab), `tooltip`, `popover`, `breadcrumbs`, `nav_tabs`, `nav_item`, `nav_tab_content`, `modal_scaffold`, `alert_dialog`, `confirm_dialog`, `data_table`, `countdown_timer`

### 6. gui.button is a form submit — NOT a link

`gui.button()` renders `<button type="submit">`. It triggers a server round-trip, not client-side navigation.

```python
# WRONG — button inside <a> won't navigate (submit intercepts click)
with gui.tag("a", href="#section"):
    gui.button("Go to section", key="nav")

# CORRECT — use <a> tag styled as button for navigation
with gui.tag("a", href="#section", className="btn btn-sm btn-outline-secondary"):
    gui.html("Go to section")

# CORRECT — use gui.anchor for styled link-button
gui.anchor("Visit page", href="/page", type="primary")

# CORRECT — gui.button for actions that need server processing
if gui.button("Submit", key="submit_btn", type="primary"):
    # This runs on the server when clicked
    process_form()
```

## Quick Reference — All Components

### Layout & Structure

| Component | Returns | Description |
|-----------|---------|-------------|
| `gui.div(**props)` | NestingCtx | Generic container (`<div>`) |
| `gui.tag(tag_name, **props)` | NestingCtx | Any HTML tag |
| `gui.columns(spec, responsive=True)` | tuple[NestingCtx, ...] | Multi-column layout. `spec`: int or list of weights |
| `gui.center(direction, className)` | NestingCtx | Centered flex container |
| `gui.expander(label, expanded=False, key)` | NestingCtx | Collapsible section |
| `gui.link(to=url, **props)` | NestingCtx | Client-side router link |
| `sidebar_layout(key, session, disabled)` | tuple[NestingCtx, NestingCtx] | Sidebar + page content (from `widgets.sidebar`) |

### Content & Text

| Component | Returns | Description |
|-----------|---------|-------------|
| `gui.write(*objs, unsafe_allow_html, **props)` | None | Primary output — renders Markdown |
| `gui.markdown(body, line_clamp, **props)` | None | Explicit Markdown block |
| `gui.text(body, **props)` | None | Preformatted text (`<pre>`) |
| `gui.html(body, **props)` | None | Raw HTML (icons, custom markup) |
| `gui.caption(body, className)` | None | Small muted text |
| `gui.newline()` | None | Line break |
| `gui.error(body, icon="fire")` | None | Error message box |
| `gui.success(body, icon="check")` | None | Success message box |

### Inputs — Text

| Component | Returns | Key params |
|-----------|---------|------------|
| `gui.text_input(label, key, placeholder, help)` | str | Single-line text |
| `gui.text_area(label, key, height, placeholder)` | str | Multi-line text |
| `gui.password_input(label, key, placeholder)` | str | Masked input |
| `gui.code_editor(value, key, label)` | str | Code editor with highlighting |

### Inputs — Numeric & Date

| Component | Returns | Key params |
|-----------|---------|------------|
| `gui.number_input(label, min_value, max_value, value, step, key)` | float | Numeric input |
| `gui.slider(label, min_value, max_value, value, step, key)` | float | Range slider |
| `gui.date_input(label, key)` | datetime \| None | Date picker |

### Inputs — Selection
| Component | Returns | Key params |
|-----------|---------|------------|
| `gui.checkbox(label, value=False, key)` | bool | Checkbox |
| `gui.switch(label, value=False, key, size)` | bool | Toggle switch (`size="small"` or `"large"`) |
| `gui.radio(label, options, key)` | T \| None | Vertical radio buttons |
| `gui.horizontal_radio(label, options, key)` | T \| None | Inline toggle buttons |
| `gui.selectbox(label, options, key, allow_none)` | T \| None | Single-select dropdown |
| `gui.multiselect(label, options, key, allow_none)` | list[T] | Multi-select dropdown |

### File Upload
| Component | Returns | Key params |
|-----------|---------|------------|
| `gui.file_uploader(label, accept, accept_multiple_files, key)` | str \| list[str] \| None | File upload |

### Buttons & Links
| Component | Returns | Description |
|-----------|---------|-------------|
| `gui.button(label, key, type, disabled)` | bool | Form submit button. Types: `"primary"`, `"secondary"`, `"tertiary"`, `"link"` |
| `gui.anchor(label, href, type, new_tab)` | None | Styled link (looks like button) |
| `gui.url_button(url)` | None | External link icon button |
| `gui.download_button(label, url, key, type)` | bool | File download button |

### Media
| Component | Returns | Key params |
|-----------|---------|------------|
| `gui.image(src, caption, alt, href, show_download_button)` | None | Image display |
| `gui.video(src, caption, autoplay, show_download_button)` | None | Video player |
| `gui.audio(src, caption, show_download_button)` | None | Audio player |

### Navigation
| Component | Returns | Description |
|-----------|---------|-------------|
| `gui.tabs(labels)` | list[NestingCtx] | Rounded tab panels |
| `gui.controllable_tabs(labels, key)` | tuple[list[NestingCtx], int] | Tabs with state control |
| `gui.nav_tabs()` / `gui.nav_item(href, active)` / `gui.nav_tab_content()` | NestingCtx | Underline-style tabs |
| `gui.breadcrumbs(divider)` / `gui.breadcrumb_item(inner_html, link_to)` | NestingCtx / None | Breadcrumb nav |

### Overlays & Feedback
| Component | Returns | Description |
|-----------|---------|-------------|
| `gui.tooltip(content, placement)` | NestingCtx | Hover tooltip wrapper |
| `gui.popover(placement)` | tuple[NestingCtx, NestingCtx] | Popover (trigger, content) |
| `gui.pill(title, text_bg)` | None | Badge/pill. `text_bg`: `"primary"`, `"secondary"`, `"light"`, `"dark"` |
| `gui.modal_scaffold(large)` | tuple[NestingCtx, NestingCtx, NestingCtx] | Modal (header, body, footer) |
| `gui.alert_dialog(ref, modal_title)` | NestingCtx | Alert modal body |
| `gui.confirm_dialog(ref, modal_title, confirm_label)` | NestingCtx | Confirm modal body |
| `gui.use_alert_dialog(key)` | AlertDialogRef | Alert dialog state hook |
| `gui.use_confirm_dialog(key)` | ConfirmDialogRef | Confirm dialog state hook |
| `gui.button_with_confirm_dialog(ref, trigger_label, modal_title, confirm_label)` | NestingCtx | Button that opens confirm dialog |

### Data Display
| Component | Returns | Description |
|-----------|---------|-------------|
| `gui.json(value, expanded, depth)` | None | Interactive JSON viewer |
| `gui.data_table(file_url_or_cells)` | NestingCtx | Data table |
| `gui.table(df)` | None | Pandas DataFrame table |
| `gui.plotly_chart(figure_or_data)` | None | Plotly chart |

### Styling & Scripting
| Component | Returns | Description |
|-----------|---------|-------------|
| `gui.styled(css)` | NestingCtx | Scoped CSS — `&` replaced with unique class |
| `gui.js(src, **kwargs)` | None | Inject `<script>` tag |
| `gui.countdown_timer(end_time, delay_text)` | NestingCtx | Countdown widget |

### State
| Component | Returns | Description |
|-----------|---------|-------------|
| `gui.session_state` | dict | Per-user state. All inputs read/write here via `key` |
| `gui.session_state.get(key, default)` | Any | Read state |
| `gui.session_state[key] = value` | None | Write state |

## Patterns

### Sidebar layout

```python
from widgets.sidebar import sidebar_layout

# In route handler:
sidebar, page_content = sidebar_layout(key="my-sidebar", session=request.session)

with sidebar:
    gui.write("**Nav**")
    for item in items:
        with gui.tag("a", href=f"#{item.id}", className="btn btn-sm btn-outline-secondary text-start border-0"):
            gui.html(item.label)

with page_content:
    render_main_content()
```

Open/close via JS events:
```python
# Open button
open_js = "window.dispatchEvent(new Event('my-sidebar:open'))"
with gui.tag("button", className="btn btn-sm btn-outline-secondary", onClick=open_js):
    gui.html('<i class="fa-solid fa-bars"></i>')

# Close button
close_js = "window.dispatchEvent(new Event('my-sidebar:close'))"
with gui.tag("button", className="btn btn-sm", onClick=close_js):
    gui.html('<i class="fa-solid fa-xmark"></i>')
```

The sidebar auto-shows/hides elements with class `{key}-button` on close/open.

### Modal / confirm dialog

```python
ref = gui.use_confirm_dialog("delete_dialog")
with gui.button_with_confirm_dialog(
    ref=ref,
    trigger_label="Delete",
    trigger_type="primary",
    modal_title="Are you sure?",
    modal_content="This cannot be undone.",
    confirm_label="Delete",
    confirm_className="btn-danger",
):
    pass
if ref.pressed_confirm:
    do_delete()
```

### Popover

```python
trigger, content = gui.popover()
with trigger:
    gui.button("Info", key="info_btn")
with content:
    gui.write("Popover body — any gui components")
```

### Responsive columns

```python
# Equal columns (stack on mobile by default)
col1, col2 = gui.columns(2)

# Weighted columns
narrow, wide = gui.columns([1, 3])

# Non-responsive (stays side-by-side on mobile)
col1, col2 = gui.columns(2, responsive=False)
```

### Tabs

```python
tab1, tab2 = gui.tabs(["Tab A", "Tab B"])
with tab1:
    gui.write("Content A")
with tab2:
    gui.write("Content B")
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Using `gui.styled` for spacing/colors | Use Bootstrap classes: `className="p-3 bg-light"` |
| Using `style=dict(...)` for flex layout | Use `className="d-flex gap-2 align-items-center"` |
| Putting `gui.button` inside `<a>` tag | Use `gui.tag("a", className="btn btn-sm ...")` or `gui.anchor()` |
| Using `gui.write` for raw HTML (icons) | Use `gui.html('<i class="fa-solid fa-star"></i>')` |
| Forgetting `unsafe_allow_html=True` on code blocks with `&` | Pass `unsafe_allow_html=True` to `gui.write` |
| Using `gui.write` inside `gui.styled` with custom colors | `gui-md-container` class overrides colors — use `gui.html()` instead |
| Missing `key` on interactive components | Every input/button needs a unique `key` for state tracking |
| Using emoji for icons | Use Font Awesome: `<i class="fa-solid fa-check"></i>` |
| Creating new `.html` templates | Use `gui.*` components — never build raw HTML strings |
