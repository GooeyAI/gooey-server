import jinja2
import jinja2.meta
import jinja2.sandbox

import gooey_ui as st


def prompt_vars_widget(input_prompt: str, key: str = "variables"):
    env = jinja2.sandbox.SandboxedEnvironment()
    try:
        parsed = env.parse(input_prompt)
    except jinja2.exceptions.TemplateSyntaxError as e:
        st.error(e.message)
        return
    template_vars = jinja2.meta.find_undeclared_variables(parsed)
    if not template_vars:
        return
    st.write("##### ⌥ Variables")
    old_state = st.session_state.get(key, {})
    new_state = {}
    for name in sorted(template_vars):
        if name in st.session_state:
            continue
        var_key = f"__{key}_{name}"
        st.session_state.setdefault(var_key, old_state.get(name, ""))
        new_state[name] = st.text_area("`" + name + "`", key=var_key, height=50)
    st.session_state[key] = new_state


def render_prompt_vars(prompt: str, *, variables: dict | None, state: dict | None):
    env = jinja2.sandbox.SandboxedEnvironment()
    context = (state or {}) | (variables or {})
    context = {k: str(v).strip() if v else "" for k, v in context.items()}
    return env.from_string(prompt).render(**context)
