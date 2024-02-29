import gooey_ui as st


def lipsync_settings():
    st.write(
        """
        ##### ⌖ Lipsync Face Padding
        Adjust the detected face bounding box. Often leads to improved results.  
        Recommended to give at least 10 padding for the chin region. 
        """
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.slider(
            "Head",
            min_value=0,
            max_value=50,
            key="face_padding_top",
        )
    with col2:
        st.slider(
            "Chin",
            min_value=0,
            max_value=50,
            key="face_padding_bottom",
        )
    with col3:
        st.slider(
            "Left Cheek",
            min_value=0,
            max_value=50,
            key="face_padding_left",
        )
    with col4:
        st.slider(
            "Right Cheek",
            min_value=0,
            max_value=50,
            key="face_padding_right",
        )
