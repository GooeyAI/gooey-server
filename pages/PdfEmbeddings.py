import datetime
import json
import os
import re
import subprocess
import tempfile
from collections import deque

import numpy as np
import openai
import pdftotext
import requests
import streamlit as st
from requests_html import HTML

from daras_ai.face_restoration import map_parallel
from daras_ai_v2 import settings

url = st.text_input("url")
st.write("_or_")
input_files = st.file_uploader(
    "pdf", type=["pdf", "txt", "docx", "doc", "md"], accept_multiple_files=True
)

max_context_words = 200
scroll_jump = 5
top_p = 3


@st.cache_data()
def pdf_to_text(f):
    return list(pdftotext.PDF(f))


@st.cache_data()
def pandoc_convert(f, to="plain"):
    with tempfile.NamedTemporaryFile(
        suffix="." + os.path.basename(f.name)
    ) as infile, tempfile.NamedTemporaryFile("r") as outfile:
        infile.write(f.getbuffer())
        args = [
            "pandoc",
            "--standalone",
            infile.name,
            "--to",
            to,
            "--output",
            outfile.name,
        ]
        print("\t$", " ".join(args))
        subprocess.check_call(args)
        return outfile.read()


# language=regexp
line_break = r"\s*[\r\n\f\v]\s*"

# split long text at sentence ends
fragment_split_re = re.compile(
    r"("
    # whitespace & line break
    + line_break
    # OR
    + r"|"
    # sentence end chars
    + r"s*([\.\!\?])"
    + r")"
    # followed by whitespace & line break
    + line_break
)


def split_text_into_fragments(text):
    last_idx = 0
    for match in fragment_split_re.finditer(text):
        end_char = match.group(2) or ""
        frag = text[last_idx : match.start()] + end_char
        frag = frag.strip()
        if frag:
            yield frag
        last_idx = match.end()


word_breaks_re = re.compile(
    r"\s*"
    # hypon/en-dash/em-dash
    + r"[\-\–\—]+"
    # followed by whitespace & line break
    + line_break
)

docs = []
if input_files:
    pdf_pages = []
    for f in input_files:
        ext = os.path.splitext(f.name)[-1].lower()
        match ext:
            case ".pdf":
                pdf_pages.extend(pdf_to_text(f))
            case ".docx" | ".doc" | ".md":
                pdf_pages.append(pandoc_convert(f))
            case ".txt":
                pdf_pages.append(f.getvalue().decode())

    with st.expander(f"{len(pdf_pages)} pages"):
        for idx, page in enumerate(pdf_pages[:50]):
            st.text_area(f"page {idx}", page, 400)

    full_text = "\n\n".join(pdf_pages)

elif url:
    html = HTML(html=requests.get(url).text)
    full_text = html.full_text

else:
    st.stop()

# handle word breaks to the next line
full_text = word_breaks_re.sub(" - ", full_text)
# split text into fragments
all_frags = list(split_text_into_fragments(full_text))

window = deque()

for idx in range(len(all_frags)):
    # add this para to the window
    window.append(all_frags[idx])

    # keep increasing the window until your either reach the end, or the context size is exhausted
    try:
        next_frag = all_frags[idx + 1]
    except IndexError:
        pass
    else:
        next_window = [*window, next_frag]
        next_window_words = sum(len(re.split(r"\s+", para)) for para in next_window)
        if next_window_words <= max_context_words:
            continue

    # accept this window as a doc
    docs.append("\n".join(window))

    # scroll jump - remove paras from the start of window
    for _ in range(scroll_jump):
        try:
            window.popleft()
        except IndexError:
            break

with st.expander(f"{len(docs)} documents"):
    for idx, doc in enumerate(docs[:50]):
        st.text_area(f"doc {idx}", doc, 200)
with open("parts.json", "w") as f:
    json.dump(docs, f, indent=" " * 2)
query = st.text_input("query")
if not (query and docs):
    st.stop()


@st.cache_data(show_spinner=False)
def get_embedding(text: str) -> list[float]:
    openai.api_key = settings.OPENAI_API_KEY
    result = openai.Embedding.create(model="text-embedding-ada-002", input=text)
    return result["data"][0]["embedding"]


def vector_similarity(x: list[float], y: list[float]) -> float:
    """
    Returns the similarity between two vectors.

    Because OpenAI Embeddings are normalized to length 1, the cosine similarity is the same as the dot product.
    """
    return np.dot(np.array(x), np.array(y))


def get_document_similarities(query, docs):
    query_embedding = get_embedding(query)
    embeddings = map_parallel(get_embedding, docs)
    return sorted(
        [
            (vector_similarity(query_embedding, doc_embedding), doc_index)
            for doc_index, doc_embedding in enumerate(embeddings)
            if vector_similarity(query_embedding, doc_embedding) > 0.7
        ],
        reverse=True,
    )


with st.spinner("getting embeddings..."):
    document_similarities = get_document_similarities(query, docs)[:top_p]

search_results = "\n".join(
    f'''[{idx + 1}] """\n{docs[doc_idx]}\n"""'''
    for idx, (similarity, doc_idx) in enumerate(document_similarities)
)


prompt = (
    """Generate a concise, factoid Answer the for the following Question soely based on the provided web Search Results. \
If the Search Results do not contain enough information, refuse to Answer the Question. \
Use an unbiased, succinct, and funny tone. \
Use this current date and time: {{ datetime.utcnow }}. \
Combine Search Results together into a coherent answer. \
Remember to cite the search results using [${number}] notation in your answer.

Search Results: 
{{ search_results }}
Question: {{ request.query }}
Answer:""".replace(
        "{{ datetime.utcnow }}",
        datetime.datetime.utcnow().isoformat(),
    )
    .replace(
        "{{ request.query }}",
        query,
    )
    .replace("{{ search_results }}", search_results)
)

with st.expander("prompt"):
    st.text_area(f"prompt", prompt, 400)

answer = st.cache_data(openai.Completion.create)(
    model="text-davinci-003",
    prompt=prompt,
    max_tokens=256,
    temperature=0.1,
)["choices"][0]["text"]

st.text_area("answer", answer, 400)
