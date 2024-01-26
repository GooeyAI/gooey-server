import os
import typing

import gooey_ui as st
from daras_ai_v2 import settings
from daras_ai_v2.asr import AsrModels, google_translate_language_selector
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.search_ref import CitationStyles

_user_media_url_prefix = os.path.join(
    "storage.googleapis.com", settings.GS_BUCKET_NAME, settings.GS_MEDIA_PATH
)


def is_user_uploaded_url(url: str) -> bool:
    return _user_media_url_prefix in url


def document_uploader(
    label: str,
    key: str = "documents",
    accept: typing.Iterable[str] = (
        ".pdf",
        ".txt",
        ".docx",
        ".md",
        ".html",
        ".wav",
        ".ogg",
        ".mp3",
        ".aac",
    ),
    accept_multiple_files=True,
) -> list[str] | str:
    documents = st.session_state.get(key) or []
    if isinstance(documents, str):
        documents = [documents]
    if st.session_state.get(f"__custom_checkbox_{key}"):
        if accept_multiple_files:
            widget = st.text_area
            kwargs = dict(height=150)
        else:
            widget = st.text_input
            kwargs = {}
        text_value = widget(
            label,
            value="\n".join(documents),
            style={
                "whiteSpace": "pre",
                "overflowWrap": "normal",
                "overflowX": "scroll",
                "fontFamily": "monospace",
                "fontSize": "0.9rem",
            },
            **kwargs,
        )
        if accept_multiple_files:
            st.session_state[key] = text_value.strip().splitlines()
        else:
            st.session_state[key] = text_value
    else:
        st.file_uploader(
            label,
            key=key,
            accept=accept,
            accept_multiple_files=accept_multiple_files,
        )
    st.checkbox("Upload Links in Bulk", key=f"__custom_checkbox_{key}")
    return st.session_state.get(key, [])


def doc_search_settings(
    asr_allowed: bool = False,
    keyword_instructions_allowed: bool = False,
):
    from daras_ai_v2.vector_search import DocSearchRequest

    st.write("##### 🔎 Document Search Settings")

    if "citation_style" in st.session_state:
        enum_selector(
            CitationStyles,
            label="###### Citation Style",
            key="citation_style",
            use_selectbox=True,
            allow_none=True,
        )

    st.text_area(
        """
###### 👁‍🗨 Summarization Instructions
Prompt to transform the conversation history into a vector search query.  \\
These instructions run before the workflow performs a search of the knowledge base documents and should summarize the conversation into a VectorDB query most relevant to the user's last message. In general, you shouldn't need to adjust these instructions.
        """,
        key="query_instructions",
        height=300,
    )
    if keyword_instructions_allowed:
        st.text_area(
            """
###### 🔑 Keyword Extraction 
Prompt to extract a query for hybrid BM25 search.  \\
These instructions run after the Summarization Instructions above and can use its result via `{{ final_search_query }}`. In general, you shouldn't need to adjust these instructions.
        """,
            key="keyword_instructions",
            height=300,
        )

    dense_weight_ = DocSearchRequest.__fields__["dense_weight"]
    st.slider(
        label=f"###### {dense_weight_.field_info.title}\n{dense_weight_.field_info.description}",
        key=dense_weight_.name,
        min_value=dense_weight_.field_info.ge,
        max_value=dense_weight_.field_info.le,
    )

    st.number_input(
        label="""
###### Max Citations
The maximum number of document search citations.
""",
        key="max_references",
        min_value=1,
        max_value=20,
    )

    st.number_input(
        label="""
###### Max Snippet Words

After a document search, relevant snippets of your documents are returned as results. This setting adjusts the maximum number of words in each snippet. A high snippet size allows the LLM to access more information from your document results, at the cost of being verbose and potentially exhausting input tokens (which can cause a failure of the copilot to respond). Default: 300
""",
        key="max_context_words",
        min_value=10,
        max_value=500,
    )

    st.number_input(
        label="""
###### Overlapping Snippet Lines
Your knowledge base documents are split into overlapping snippets. This settings adjusts how much those snippets overlap. In general you shouldn't need to adjust this. Default: 5

""",
        key="scroll_jump",
        min_value=1,
        max_value=50,
    )

    if not asr_allowed:
        return

    st.write("---")
    st.write(
        """
        ##### 🎤 Knowledge Base Speech Recognition
        <font color="grey">If your knowledge base documents contain audio or video files, we'll transcribe and optionally translate them to English, given we've found most vectorDBs and LLMs perform best in English (even if their final answers are translated into another language).</font>
        """,
        unsafe_allow_html=True,
    )

    enum_selector(
        AsrModels,
        label="###### ASR Model",
        key="selected_asr_model",
        allow_none=True,
        use_selectbox=True,
    )
    google_translate_language_selector()
