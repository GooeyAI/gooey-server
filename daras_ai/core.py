import importlib
import inspect
import pkgutil
import types
from functools import wraps
from pathlib import Path

import streamlit as st
import typing

OUTPUT_STEPS = "output_steps"

COMPUTE_STEPS = "compute_steps"

INPUT_STEPS = "input_steps"

STEPS_REPO = {
    INPUT_STEPS: {},
    COMPUTE_STEPS: {},
    OUTPUT_STEPS: {},
}


def daras_ai_step(verbose_name, *, is_input=False, is_output=False, is_expanded=False):
    def decorator(fn):
        @wraps(fn)
        def wrapper(idx, delete, variables, state):
            with st.expander(verbose_name, expanded=is_expanded):
                if st.button("🗑", help=f"Delete {verbose_name} {idx + 1}"):
                    delete()
                    return
                fn(idx=idx, variables=variables, state=state)

        if is_input:
            steps_key = INPUT_STEPS
        elif is_output:
            steps_key = OUTPUT_STEPS
        else:
            steps_key = COMPUTE_STEPS

        STEPS_REPO[steps_key][wrapper.__name__] = wrapper
        wrapper.verbose_name = verbose_name
        return wrapper

    return decorator


def var_selector(label, *, state, variables, **kwargs):
    options = ["", *variables.keys()]
    try:
        index = options.index(state.get(label, ""))
    except IndexError:
        index = 0
    selected_var = st.selectbox(
        label,
        options=options,
        index=index,
        **kwargs,
    )
    state.update({label: selected_var})
    return selected_var


def import_all() -> typing.Dict[str, types.ModuleType]:
    """ "imports all modules in the package of the caller"""

    caller_frame = inspect.stack()[1]
    caller_dir = str(Path(caller_frame.filename).parent)
    caller_module = inspect.getmodule(caller_frame[0])
    caller_package = caller_module.__package__

    modules = {}

    for info in pkgutil.walk_packages([caller_dir]):
        if caller_dir != info.module_finder.path:
            # exclude modules that lie outside of the current package
            continue

        name = f"{caller_package}.{info.name}"
        modules[name] = importlib.import_module(name)

    return modules
