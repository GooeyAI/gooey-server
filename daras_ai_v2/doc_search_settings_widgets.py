import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from daras_ai.image_input import upload_st_file
from daras_ai_v2 import settings
from daras_ai_v2.asr import AsrModels, google_translate_language_selector
from daras_ai_v2.enum_selector_widget import enum_selector


def is_user_uploaded_url(url: str) -> bool:
    return f"storage.googleapis.com/{settings.GS_BUCKET_NAME}/daras_ai" in url


def document_uploader(
    label: str,
    key="documents",
    type=("pdf", "txt", "docx", "md", "html", "wav", "ogg", "mp3", "aac"),
):
    st.write(label)
    documents = st.session_state.get(key, [])
    has_custom_urls = not all(map(is_user_uploaded_url, documents))
    if st.checkbox("Enter Custom URLs", value=has_custom_urls):
        text_value = st.text_area(
            label,
            label_visibility="collapsed",
            value="\n".join(documents),
            height=150,
        )
        st.session_state[key] = text_value.splitlines()
    else:
        st.file_uploader(
            label,
            label_visibility="collapsed",
            key=f"__{key}_files",
            upload_key=key,
            type=type,
            accept_multiple_files=True,
        )


def validate_upload_documents(
    *,
    key="documents",
    required=True,
) -> None:
    """
    Validate the user documents, upload them and save to the session state.

    Args:
        key: the key to save the documents to in the session state
        required: whether the documents are required or not

    Returns:
        None
    """
    uploaded_files: list[UploadedFile] | None = st.session_state.get(f"__{key}_files")
    if uploaded_files:
        uploaded = []
        for f in uploaded_files:
            # if the file is a urls.txt file
            if f.name == "urls.txt":
                # add the urls from the file
                uploaded.extend(f.getvalue().decode().splitlines())
            else:
                # add the url after uploading file
                uploaded.append(upload_st_file(f))
        # save the urls to the session state
        st.session_state[key] = uploaded
    if required:
        assert st.session_state.get(key), "Please provide at least 1 Document"


def doc_search_settings():
    st.write("##### 🔎 Search Settings")

    st.number_input(
        label="""
###### Max References
The maximum number of References to include from the source document.
""",
        key="max_references",
        min_value=1,
        max_value=10,
    )

    st.number_input(
        label="""
###### Max context size (in words)

The maximum size of each split of the document.\\
A high context size allows GPT to access a greater chunk of information from the source document, 
at the cost of being too verbose, and running out of input tokens. 
""",
        key="max_context_words",
        min_value=10,
        max_value=500,
    )

    st.number_input(
        label="""
###### Scroll Jump
We split the documents into chunks by scrolling through it.\\
If scroll jump is too high, there might not be enough overlap between the chunks to answer the questions accurately.
""",
        key="scroll_jump",
        min_value=1,
        max_value=50,
    )

    st.write("---")
    st.write("##### 🎤 Speech Recognition Settings")

    enum_selector(
        AsrModels,
        label="###### ASR Model",
        key="selected_asr_model",
        allow_none=True,
        use_selectbox=True,
    )
    google_translate_language_selector()
