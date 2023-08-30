import gooey_ui as st

from daras_ai_v2 import settings
from daras_ai_v2.asr import AsrModels, google_translate_language_selector
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.search_ref import CitationStyles


def is_user_uploaded_url(url: str) -> bool:
    return f"storage.googleapis.com/{settings.GS_BUCKET_NAME}/daras_ai" in url


def document_uploader(
    label: str,
    key="documents",
    accept=(".pdf", ".txt", ".docx", ".md", ".html", ".wav", ".ogg", ".mp3", ".aac"),
):
    st.write(label, className="gui-input")
    documents = st.session_state.get(key) or []
    has_custom_urls = not all(map(is_user_uploaded_url, documents))
    custom_key = "__custom_" + key
    if st.checkbox("Enter Custom URLs", value=has_custom_urls):
        if not custom_key in st.session_state:
            st.session_state[custom_key] = "\n".join(documents)
        text_value = st.text_area(
            label,
            key=custom_key,
            label_visibility="collapsed",
            height=150,
            style={
                "whiteSpace": "pre",
                "overflowWrap": "normal",
                "overflowX": "scroll",
                "fontFamily": "monospace",
                "fontSize": "0.9rem",
            },
        )
        st.session_state[key] = text_value.strip().splitlines()
    else:
        st.session_state.pop(custom_key, None)
        st.file_uploader(
            label,
            label_visibility="collapsed",
            key=key,
            accept=accept,
            accept_multiple_files=True,
        )


def doc_search_settings():
    st.write("##### 🔎 Document Search Settings")

    if "citation_style" in st.session_state:
        enum_selector(
            CitationStyles,
            label="###### Citation Style",
            key="citation_style",
            use_selectbox=True,
            allow_none=True,
        )

    st.number_input(
        label="""
###### Max References
The maximum number of References to include from the source document.
""",
        key="max_references",
        min_value=1,
        max_value=20,
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
