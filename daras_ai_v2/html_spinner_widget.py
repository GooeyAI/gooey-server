import streamlit as st

html_spinner_css = """
<style>
    .loader {
      display: inline-block;
      border: 4px solid rgba(255, 255, 255, 0.2);
      border-top: 4px solid #03dac5;
      border-radius: 50%;
      width: 35px;
      height: 35px;
      animation: spin 1s linear infinite;
    }
    
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    
    .loader-text {
        padding-left: 8px; 
        padding-top: 2px; 
        vertical-align: top; 
        display: inline-block; 
        font-size: 1.1rem;
    }
</style>
"""


def html_spinner(text: str):
    st.markdown(
        f"""
        <div style="padding-top: 8px; padding-bottom: 8px;">
        <div class="loader"></div>
        <div class="loader-text">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
