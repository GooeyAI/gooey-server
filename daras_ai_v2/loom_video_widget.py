import streamlit as st


def loom_video(video_id: str):
    st.markdown(
        f"""
        <div style="position: relative; padding-bottom: 56.25%; height: 0;"><iframe src="https://www.loom.com/embed/{video_id}" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe></div>
        """,
        unsafe_allow_html=True,
    )
