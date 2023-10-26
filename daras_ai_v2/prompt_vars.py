from datetime import datetime
from types import SimpleNamespace

import jinja2
import jinja2.meta
import jinja2.sandbox

import gooey_ui as st


def prompt_vars_widget(*keys: str, variables_key: str = "variables"):
    # find all variables in the prompts
    env = jinja2.sandbox.SandboxedEnvironment()
    template_vars = set()

    err = None
    for k in keys:
        try:
            parsed = env.parse(st.session_state.get(k, ""))
        except jinja2.exceptions.TemplateSyntaxError as e:
            err = e
        else:
            template_vars |= jinja2.meta.find_undeclared_variables(parsed)

    # don't mistake globals for vars
    template_vars -= set(context_globals().keys())

    if not (template_vars or err):
        return

    st.write("##### ⌥ Variables")
    old_state = st.session_state.get(variables_key, {})
    new_state = {}
    for name in sorted(template_vars):
        if name in st.session_state:
            continue
        var_key = f"__{variables_key}_{name}"
        st.session_state.setdefault(var_key, old_state.get(name, ""))
        new_state[name] = st.text_area("`" + name + "`", key=var_key, height=300)
    st.session_state[variables_key] = new_state

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
            utcnow=datetime.utcnow().strftime("%B %d, %H:%M"),
        ),
    }
