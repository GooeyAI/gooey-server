import json
import typing
from datetime import datetime
from types import SimpleNamespace

import jinja2
import jinja2.meta
import jinja2.sandbox

import gooey_ui as st


def variables_input(
    *,
    template_keys: typing.Iterable[str],
    label: str = "###### ⌥ Variables",
    key: str = "variables",
    allow_add: bool = False,
):
    from daras_ai_v2.workflow_url_input import del_button

    # find all variables in the prompts
    env = jinja2.sandbox.SandboxedEnvironment()
    template_var_names = set()

    err = None
    for k in template_keys:
        try:
            parsed = env.parse(st.session_state.get(k, ""))
        except jinja2.exceptions.TemplateSyntaxError as e:
            err = e
        else:
            template_var_names |= jinja2.meta.find_undeclared_variables(parsed)

    old_vars = st.session_state.get(key, {})

    var_add_key = f"--{key}:add_btn"
    var_name_key = f"--{key}:add_name"
    if st.session_state.pop(var_add_key, None):
        if var_name := st.session_state.pop(var_name_key, None):
            old_vars[var_name] = ""

    all_var_names = (
        (template_var_names | set(old_vars))
        - set(context_globals().keys())  # dont show global context variables
        - set(st.session_state.keys())  # dont show other session state variables
    )

    st.session_state[key] = new_vars = {}
    title_shown = False
    for name in sorted(all_var_names):
        var_key = f"--{key}:{name}"

        del_key = f"--{var_key}:del"
        if st.session_state.get(del_key, None):
            continue

        if not title_shown:
            st.write(label)
            title_shown = True

        col1, col2 = st.columns([11, 1], responsive=False)
        with col1:
            value = old_vars.get(name)
            try:
                new_text_value = st.session_state[var_key]
            except KeyError:
                if value is None:
                    value = ""
                is_json = isinstance(value, (dict, list))
                if is_json:
                    value = json.dumps(value, indent=2)
                st.session_state[var_key] = str(value)
            else:
                try:
                    value = json.loads(new_text_value)
                    is_json = isinstance(value, (dict, list))
                    if not is_json:
                        value = new_text_value
                except json.JSONDecodeError:
                    is_json = False
                    value = new_text_value
            new_vars[name] = value

            st.text_area(
                "**```" + name + "```**" + (" (JSON)" if is_json else ""),
                key=var_key,
                height=300,
            )
        if name not in template_var_names:
            with col2, st.div(className="pt-3 mt-4"):
                del_button(key=del_key)

    if allow_add:
        if not title_shown:
            st.write(label)
        st.newline()
        col1, col2, _ = st.columns([6, 2, 4], responsive=False)
        with col1:
            with st.div(style=dict(fontFamily="var(--bs-font-monospace)")):
                st.text_input(
                    "",
                    key=var_name_key,
                    placeholder="my_var_name",
                )
        with col2:
            st.button(
                '<i class="fa-regular fa-add"></i> Add',
                key=var_add_key,
                type="tertiary",
            )

    if err:
        st.error(f"{type(err).__qualname__}: {err.message}")


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
