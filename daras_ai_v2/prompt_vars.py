import json
import typing
from datetime import datetime
from types import SimpleNamespace

import gooey_gui as gui
import jinja2
import jinja2.meta
import jinja2.sandbox

from daras_ai_v2 import icons


def variables_input(
    *,
    template_keys: typing.Iterable[str],
    label: str = "###### ⌥ Variables",
    description: str = "Variables let you pass custom parameters to your workflow. Access a variable in your instruction prompt with <a href='https://jinja.palletsprojects.com/en/3.1.x/templates/' target='_blank'>Jinja</a>, e.g. `{{ my_variable }}`\n  ",
    key: str = "variables",
    allow_add: bool = False,
):
    from daras_ai_v2.workflow_url_input import del_button

    def render_title_desc():
        gui.write(label)
        gui.caption(
            f"{description} <a href='/variables-help' target='_blank'>Learn more</a>.",
            unsafe_allow_html=True,
        )

    # find all variables in the prompts
    env = jinja2.sandbox.SandboxedEnvironment()
    template_var_names = set()

    err = None
    for k in template_keys:
        try:
            parsed = env.parse(gui.session_state.get(k, ""))
        except jinja2.exceptions.TemplateSyntaxError as e:
            err = e
        else:
            template_var_names |= jinja2.meta.find_undeclared_variables(parsed)

    old_vars = gui.session_state.get(key) or {}

    var_add_key = f"--{key}:add_btn"
    var_name_key = f"--{key}:add_name"
    if gui.session_state.pop(var_add_key, None):
        if var_name := gui.session_state.pop(var_name_key, None):
            old_vars[var_name] = ""

    all_var_names = (
        (template_var_names | set(old_vars))
        - set(context_globals().keys())  # dont show global context variables
        - set(gui.session_state.keys())  # dont show other session state variables
    )

    new_vars = {}
    if all_var_names:
        gui.session_state[key] = new_vars
    title_shown = False
    for name in sorted(all_var_names):
        var_key = f"--{key}:{name}"

        del_key = f"--{var_key}:del"
        if gui.session_state.get(del_key, None):
            continue

        if not title_shown:
            render_title_desc()
            title_shown = True

        col1, col2 = gui.columns([11, 1], responsive=False)
        with col1:
            displayed_value = stored_value = old_vars.get(name)
            try:
                displayed_value = gui.session_state[var_key]
            except KeyError:
                if stored_value is None:
                    displayed_value = ""
                is_json = isinstance(stored_value, (dict, list))
                if is_json:
                    displayed_value = json.dumps(stored_value, indent=2)
                gui.session_state[var_key] = str(displayed_value)
            else:
                try:
                    stored_value = json.loads(displayed_value)
                except json.JSONDecodeError:
                    is_json = False
                else:
                    is_json = isinstance(stored_value, (dict, list))
                if not is_json:
                    stored_value = displayed_value

            new_vars[name] = stored_value

            gui.text_area(
                "**```" + name + "```**" + (" (JSON)" if is_json else ""),
                key=var_key,
                height=300,
            )
        if name not in template_var_names:
            with col2, gui.div(className="pt-3 mt-4"):
                del_button(key=del_key)

    if allow_add:
        if not title_shown:
            render_title_desc()
        gui.newline()
        col1, col2, _ = gui.columns([6, 2, 4], responsive=False)
        with col1:
            with gui.div(style=dict(fontFamily="var(--bs-font-monospace)")):
                gui.text_input(
                    "",
                    key=var_name_key,
                    placeholder="my_var_name",
                )
        with col2:
            gui.button(
                f"{icons.add} Add",
                key=var_add_key,
                type="tertiary",
            )

    if err:
        gui.error(f"{type(err).__qualname__}: {err.message}")


def render_prompt_vars(
    prompt: str, state: dict | None, variables_key: str = "variables"
):
    env = jinja2.sandbox.SandboxedEnvironment()
    state = state.copy()
    variables = state.pop(variables_key, {})
    context = context_globals() | (state or {}) | (variables or {})
    for k, v in context.items():
        if v is None:
            context[k] = ""
        elif isinstance(v, str):
            context[k] = v.strip()
    return env.from_string(prompt).render(**context)


def context_globals():
    return {
        "datetime": SimpleNamespace(
            utcnow=datetime.utcnow().strftime("%B %d, %Y %H:%M:%S %Z"),
        ),
    }
