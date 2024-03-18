import os
import typing

from furl import furl
from sentry_sdk import capture_exception

import gooey_ui as st
from daras_ai_v2 import settings
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.gdrive_downloader import gdrive_list_urls_of_files_in_folder
from daras_ai_v2.prompt_vars import prompt_vars_widget
from daras_ai_v2.search_ref import CitationStyles

_user_media_url_prefix = os.path.join(
    "storage.googleapis.com", settings.GS_BUCKET_NAME, settings.GS_MEDIA_PATH
)

SUPPORTED_SPREADSHEET_TYPES = (
    ".csv",
    ".xlsx",
    ".xls",
    ".gsheet",
    ".ods",
    ".tsv",
    ".json",
    ".xml",
)


def is_user_uploaded_url(url: str) -> bool:
    return _user_media_url_prefix in url


def document_uploader(
    label: str,
    key: str = "documents",
    accept: typing.Iterable[str] = None,
    accept_multiple_files=True,
) -> list[str] | str:
    st.write(label, className="gui-input")
    documents = st.session_state.get(key) or []
    if isinstance(documents, str):
        documents = [documents]
    custom_key = "__custom_" + key
    if st.session_state.get(f"__custom_checkbox_{key}"):
        if not custom_key in st.session_state:
            st.session_state[custom_key] = "\n".join(documents)
        if accept_multiple_files:
            widget = st.text_area
            kwargs = dict(height=150)
        else:
            widget = st.text_input
            kwargs = {}
        text_value = widget(
            label,
            key=custom_key,
            label_visibility="collapsed",
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
            st.session_state[key] = filter(None, text_value.strip().splitlines())
        else:
            st.session_state[key] = text_value
    else:
        st.session_state.pop(custom_key, None)
        st.file_uploader(
            label,
            label_visibility="collapsed",
            key=key,
            accept=accept,
            accept_multiple_files=accept_multiple_files,
        )
    st.checkbox("Submit Links in Bulk", key=f"__custom_checkbox_{key}")
    documents = st.session_state.get(key, [])
    if accept_multiple_files:
        try:
            documents = list(_expand_gdrive_folders(documents))
        except Exception as e:
            capture_exception(e)
            st.error(f"Error expanding gdrive folders: {e}")
    st.session_state[key] = documents
    st.session_state[custom_key] = "\n".join(documents)
    return documents


def _expand_gdrive_folders(documents: list[str]) -> list[str]:
    for url in documents:
        if url.startswith("https://drive.google.com/drive/folders"):
            yield from gdrive_list_urls_of_files_in_folder(furl(url))
        else:
            yield url


def citation_style_selector():
    enum_selector(
        CitationStyles,
        label="###### Citation Style",
        key="citation_style",
        use_selectbox=True,
        allow_none=True,
    )


def query_instructions_widget():
    st.text_area(
        """
###### 👁‍🗨 Conversation Summarization
These instructions run before the knowledge base is search and should reduce the conversation into a search query most relevant to the user's last message.
        """,
        key="query_instructions",
        height=300,
    )
    prompt_vars_widget(
        "query_instructions",
    )


def keyword_instructions_widget():
    st.text_area(
        """
        ###### 🔑 Keyword Extraction 
        Instructions to create a query for keyword/hybrid BM25 search. Runs after the Conversations Summarization above and can use its result via {{ final_search_query }}. 
        """,
        key="keyword_instructions",
        height=300,
    )
    prompt_vars_widget(
        "keyword_instructions",
    )


def doc_extract_selector():
    from recipes.DocExtract import DocExtractPage
    from bots.models import PublishedRun, Workflow, PublishedRunVisibility

    options = {
        None: "---",
        DocExtractPage.get_root_published_run().get_app_url(): "Default",
    } | {
        pr.get_app_url(): pr.title
        for pr in PublishedRun.objects.filter(
            workflow=Workflow.DOC_EXTRACT,
            is_approved_example=True,
            visibility=PublishedRunVisibility.PUBLIC,
        ).exclude(published_run_id="")
    }
    st.selectbox(
        """
        ###### Create Synthetic Data
        To improve answer quality, pick a synthetic data maker workflow to scan & OCR any  images in your documents or transcribe & translate any videos. It also can synthesize a helpful FAQ. Adds ~2 minutes of one-time processing per file.
        """,
        key="doc_extract_url",
        options=options,
        format_func=lambda x: options[x],
    )


def doc_search_advanced_settings():
    from daras_ai_v2.vector_search import DocSearchRequest

    embeddings_model_selector(key="embedding_model")

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


def embeddings_model_selector(key: str):
    return enum_selector(
        EmbeddingModels,
        label="##### Embeddings Model",
        key=key,
        use_selectbox=True,
    )
