from daras_ai.core import COMPUTER_REPO


def run_compute_steps(compute_steps, variables):
    for idx, compute_step in enumerate(compute_steps):
        try:
            step_fn = COMPUTER_REPO[compute_step["name"]]
        except KeyError:
            continue
        step_fn(state=compute_step, variables=variables, idx=idx)
