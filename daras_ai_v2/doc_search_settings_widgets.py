import os
import typing

import gooey_gui as gui
from app_users.models import AppUser
from furl import furl
from sentry_sdk import capture_exception

from daras_ai_v2 import settings
from daras_ai_v2.embedding_model import EmbeddingModels
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.gdrive_downloader import gdrive_list_urls_of_files_in_folder
from daras_ai_v2.search_ref import CitationStyles

if typing.TYPE_CHECKING:
    from daras_ai_v2.base import BasePage


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
    help: str | None = None,
) -> list[str]:
    gui.write(label, className="gui-input", help=help, unsafe_allow_html=True)
    documents = gui.session_state.get(key) or []
    if isinstance(documents, str):
        documents = [documents]
    custom_key = "__custom_" + key
    if gui.session_state.get(f"__custom_checkbox_{key}"):
        if custom_key not in gui.session_state:
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
    gui.checkbox("Show as Links", key=f"__custom_checkbox_{key}")
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


def cache_knowledge_widget(page: "BasePage"):
    gui.write("###### Cache")
    gui.caption(
        """
        By default we embed your knowledge files & links and cache their contents for fast responses. 
        """
    )
    col1, col2 = gui.columns(2, style={"alignItems": "center"})
    with col1:
        gui.checkbox(
            "Always Check for Updates",
            help="With each incoming message, documents and links will be checked for changes and re-indexed. Slower but useful for dynamic webpages, Google Sheets, Docs, etc that change often.",
            tooltip_placement="bottom",
            key="check_document_updates",
        )
    with col2, gui.tooltip("Check documents for changes, re-index if needed & Run"):
        if gui.button("♻️ Refresh Cache", type="tertiary"):
            if gui.session_state.get("check_document_updates"):
                unsaved_state = {}
            else:
                unsaved_state = dict(check_document_updates=True)
            page.submit_and_redirect(unsaved_state=unsaved_state)


def doc_extract_selector(current_user: AppUser | None):
    from recipes.DocExtract import DocExtractPage

    from daras_ai_v2.workflow_url_input import workflow_url_input

    gui.write("###### Create Synthetic Data")
    gui.caption(
        f"""
        To improve answer quality, pick a [synthetic data maker workflow]({DocExtractPage.get_root_pr().get_app_url()}) to scan & OCR any  images in your documents or transcribe & translate any videos. It also can synthesize a helpful FAQ. Adds ~2 minutes of one-time processing per file.
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

    gui.slider(
        label=f"###### {field_title_desc(DocSearchRequest, 'dense_weight')}",
        key="dense_weight",
        min_value=0.0,
        max_value=1.0,
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
