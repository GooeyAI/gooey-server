import streamlit as st


def document_uploader(label: str):
    return st.file_uploader(
        label,
        key="__document_files",
        upload_key="documents",
        type=["pdf", "txt", "docx", "md", "html"],
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
