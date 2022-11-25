import requests
import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_hq
from daras_ai_v2.base import BasePage

input_files = st.file_uploader("input_files", accept_multiple_files=True)

if input_files:
    for input_file in input_files:
        with st.spinner(f"Processing {input_file.name}..."):
            input_image = upload_file_hq(input_file)
            response = requests.post(
                "https://api.gooey.ai/v1/ImageSegmentation/run",
                json={
                    "input_image": input_image,
                    "selected_model": "dis",
                    "mask_threshold": 0.8,
                },
            )
        response.raise_for_status()
        col1, col2 = st.columns(2)

        with col1:
            st.image(input_image, width=500)
        with col2:
            cutout_image = response.json()["cutout_image"]
            st.image(cutout_image, width=500)
