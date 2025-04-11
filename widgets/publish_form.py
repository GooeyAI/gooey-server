import gooey_gui as gui


def clear_publish_form():
    """Clear all published run related state from the session."""
    for key in list(gui.session_state.keys()):
        if key.startswith("published_run_"):
            gui.session_state.pop(key, None)
