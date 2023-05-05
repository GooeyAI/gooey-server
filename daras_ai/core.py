import importlib
import inspect
import pkgutil
import types
from functools import wraps
from pathlib import Path

import gooey_ui as st
import typing

OUTPUT_STEPS = "output_steps"
COMPUTE_STEPS = "compute_steps"
INPUT_STEPS = "input_steps"

STEPS_REPO = {
    INPUT_STEPS: {},
    COMPUTE_STEPS: {},
    OUTPUT_STEPS: {},
}

IO_REPO = {}
COMPUTER_REPO = {}


def daras_ai_step_computer(fn):
    COMPUTER_REPO[fn.__name__] = fn

    @wraps(fn)
    def wrapper(idx, steps, variables, state):
        fn(idx=idx, variables=variables, state=state)

    return wrapper


def daras_ai_step_io(fn):
    IO_REPO[fn.__name__] = fn

    @wraps(fn)
    def wrapper(idx, steps, variables, state):
        fn(idx=idx, variables=variables, state=state)

    return wrapper


def daras_ai_step_config(
    verbose_name, *, is_input=False, is_output=False, is_expanded=False
):
    def decorator(fn):
        @wraps(fn)
        def wrapper(idx, steps, variables, state):
            with st.expander(verbose_name, expanded=is_expanded):
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button(
                        "Move Up ⬆️",
                        help=f"Move up {verbose_name} {idx + 1}",
                        disabled=idx == 0,
                    ):
                        steps[idx], steps[idx - 1] = steps[idx - 1], steps[idx]
                        st.experimental_rerun()
                with col2:
                    if st.button(
                        "Move Down ⬇️",
                        help=f"Move down {verbose_name} {idx + 1}",
                        disabled=idx == len(steps) - 1,
                    ):
                        steps[idx], steps[idx + 1] = steps[idx + 1], steps[idx]
                        st.experimental_rerun()
                with col3:
                    if st.button("🗑 Delete", help=f"Delete {verbose_name} {idx + 1}"):
                        steps.pop(idx)
                        st.experimental_rerun()
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
