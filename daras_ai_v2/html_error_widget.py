from textwrap import dedent

import gooey_gui as gui


def html_error(body, icon="⚠️"):
    gui.write(
        f"""
<div style="background-color: rgba(255, 108, 108, 0.2); padding: 16px; border-radius: 0.25rem; display: flex; gap: 0.5rem;">
<span style="font-size: 1.25rem">{icon}</span>
<div>{dedent(body)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )
