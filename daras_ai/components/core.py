from functools import wraps

import streamlit as st

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
