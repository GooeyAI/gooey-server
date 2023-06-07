import gooey_ui as st
from gooey_ui import UploadedFile

from daras_ai.image_input import upload_st_file
from daras_ai_v2 import settings
from daras_ai_v2.asr import AsrModels, google_translate_language_selector
from daras_ai_v2.enum_selector_widget import enum_selector


def is_user_uploaded_url(url: str) -> bool:
    return f"storage.googleapis.com/{settings.GS_BUCKET_NAME}/daras_ai" in url


def document_uploader(
    label: str,
    key="documents",
    accept=(".pdf", ".txt", ".docx", ".md", ".html", ".wav", ".ogg", ".mp3", ".aac"),
):
    st.write(label)
    documents = st.session_state.get(key) or []
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
            key=key,
            accept=accept,
            accept_multiple_files=True,
        )


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
