import streamlit2 as st


def youtube_video(video_id: str):
    st.markdown(
        f"""
        <div style="position: relative; padding-bottom: 56.25%; height: 0;">
        <iframe src="https://www.youtube.com/embed/{video_id}" title="YouTube video player" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">
        </iframe></div>
        """,
        unsafe_allow_html=True,
    )


def loom_video(video_id: str):
    st.markdown(
        f"""
        <div style="position: relative; padding-bottom: 56.25%; height: 0;"><iframe src="https://www.loom.com/embed/{video_id}" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe></div>
        """,
        unsafe_allow_html=True,
    )
