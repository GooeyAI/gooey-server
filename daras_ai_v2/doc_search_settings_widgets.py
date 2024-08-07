import os
import typing

from furl import furl
from sentry_sdk import capture_exception

import gooey_gui as gui
from app_users.models import AppUser
from daras_ai_v2 import settings
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.gdrive_downloader import gdrive_list_urls_of_files_in_folder
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


def bulk_documents_uploader(
    label: str,
    key: str = "documents",
    accept: typing.Iterable[str] = None,
) -> list[str]:
    gui.write(label, className="gui-input")
    documents = gui.session_state.get(key) or []
    if isinstance(documents, str):
        documents = [documents]
    custom_key = "__custom_" + key
    if gui.session_state.get(f"__custom_checkbox_{key}"):
        if not custom_key in gui.session_state:
            gui.session_state[custom_key] = "\n".join(documents)
        widget = gui.text_area
        kwargs = dict(height=150)
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
        gui.session_state[key] = filter(None, text_value.strip().splitlines())
    else:
        gui.session_state.pop(custom_key, None)
        gui.file_uploader(
            label,
            label_visibility="collapsed",
            key=key,
            accept=accept,
            accept_multiple_files=True,
        )
    gui.checkbox("Submit Links in Bulk", key=f"__custom_checkbox_{key}")
    documents = gui.session_state.setdefault(key, [])
    try:
        documents = list(_expand_gdrive_folders(documents))
        gui.session_state[key] = documents
    except Exception as e:
        capture_exception(e)
        gui.error(f"Error expanding gdrive folders: {e}")
    gui.session_state[custom_key] = "\n".join(documents)
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
    gui.text_area(
        """
###### 👁‍🗨 Conversation Summarization
These instructions run before the knowledge base is search and should reduce the conversation into a search query most relevant to the user's last message.
        """,
        key="query_instructions",
        height=300,
    )


def keyword_instructions_widget():
    gui.text_area(
        """
        ###### 🔑 Keyword Extraction 
        Instructions to create a query for keyword/hybrid BM25 search. Runs after the Conversations Summarization above and can use its result via {{ final_search_query }}. 
        """,
        key="keyword_instructions",
        height=300,
    )


def doc_extract_selector(current_user: AppUser | None):
    from recipes.DocExtract import DocExtractPage
    from daras_ai_v2.workflow_url_input import workflow_url_input

    gui.write("###### Create Synthetic Data")
    gui.caption(
        f"""
        To improve answer quality, pick a [synthetic data maker workflow]({DocExtractPage.get_root_published_run().get_app_url()}) to scan & OCR any  images in your documents or transcribe & translate any videos. It also can synthesize a helpful FAQ. Adds ~2 minutes of one-time processing per file.
        """
    )
    workflow_url_input(
        page_cls=DocExtractPage,
        key="doc_extract_url",
        internal_state=gui.session_state.setdefault(
            "--doc_extract_url:state",
            {"url": gui.session_state.get("doc_extract_url")},
        ),
        current_user=current_user,
        allow_none=True,
    )


def doc_search_advanced_settings():
    from daras_ai_v2.vector_search import DocSearchRequest

    embeddings_model_selector(key="embedding_model")

    dense_weight_ = DocSearchRequest.__fields__["dense_weight"]
    gui.slider(
        label=f"###### {dense_weight_.field_info.title}\n{dense_weight_.field_info.description}",
        key=dense_weight_.name,
        min_value=dense_weight_.field_info.ge,
        max_value=dense_weight_.field_info.le,
    )

    gui.number_input(
        label="""
###### Max Citations
The maximum number of document search citations.
""",
        key="max_references",
        min_value=1,
        max_value=20,
    )

    gui.number_input(
        label="""
###### Max Snippet Words
After a document search, relevant snippets of your documents are returned as results.
This setting adjusts the maximum number of words in each snippet (tokens = words * 2).
A high snippet size allows the LLM to access more information from your document results, \
at the cost of being verbose and potentially exhausting input tokens (which can cause a failure of the copilot to respond).
""",
        key="max_context_words",
        min_value=10,
        max_value=500,
    )

    gui.number_input(
        label="""
###### Snippet Overlap Ratio
Your knowledge base documents are split into overlapping snippets.
This settings adjusts how much those snippets overlap (overlap tokens = snippet tokens / overlap ratio).
In general you shouldn't need to adjust this.
""",
        key="scroll_jump",
        min_value=1,
        max_value=50,
    )


def embeddings_model_selector(key: str):
    return enum_selector(
        EmbeddingModels,
        label="##### ✏ Embeddings Model",
        key=key,
        use_selectbox=True,
    )
