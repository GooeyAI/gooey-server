import streamlit as st
from furl import furl


def video_widget(url):
    f = furl(url)
    # https://muffinman.io/blog/hack-for-ios-safari-to-display-html-video-thumbnail/
    f.fragment.args["t"] = "0.001"
    st.video(f.url)
