import functools
import operator
import re
import typing

import tiktoken


# stolen from spacy https://spacy.io/api/sentencizer
default_punct_chars = ['!', '.', '?', '։', '؟', '۔', '܀', '܁', '܂', '߹', '।', '॥', '၊', '။', '።',
 '፧', '፨', '᙮', '᜵', '᜶', '᠃', '᠉', '᥄', '᥅', '᪨', '᪩', '᪪', '᪫',
 '᭚', '᭛', '᭞', '᭟', '᰻', '᰼', '᱾', '᱿', '‼', '‽', '⁇', '⁈', '⁉',
 '⸮', '⸼', '꓿', '꘎', '꘏', '꛳', '꛷', '꡶', '꡷', '꣎', '꣏', '꤯', '꧈',
 '꧉', '꩝', '꩞', '꩟', '꫰', '꫱', '꯫', '﹒', '﹖', '﹗', '！', '．', '？',
 '𐩖', '𐩗', '𑁇', '𑁈', '𑂾', '𑂿', '𑃀', '𑃁', '𑅁', '𑅂', '𑅃', '𑇅',
 '𑇆', '𑇍', '𑇞', '𑇟', '𑈸', '𑈹', '𑈻', '𑈼', '𑊩', '𑑋', '𑑌', '𑗂',
 '𑗃', '𑗉', '𑗊', '𑗋', '𑗌', '𑗍', '𑗎', '𑗏', '𑗐', '𑗑', '𑗒', '𑗓',
 '𑗔', '𑗕', '𑗖', '𑗗', '𑙁', '𑙂', '𑜼', '𑜽', '𑜾', '𑩂', '𑩃', '𑪛',
 '𑪜', '𑱁', '𑱂', '𖩮', '𖩯', '𖫵', '𖬷', '𖬸', '𖭄', '𛲟', '𝪈', '｡', '。']  # fmt: skip

pad = r"\s*"
whitespace = pad + r"(\s)" + pad
line_break = r"([\r\n\f\v])"
new_line = pad + line_break + pad
new_para = pad + line_break + pad + line_break + pad
puncts = "".join(map(re.escape, default_punct_chars))
sentence_end = pad + r"([" + puncts + r"])"

default_separators = (
    re.compile(sentence_end + new_para),
    re.compile(new_para),
    re.compile(sentence_end + new_line),
    re.compile(sentence_end + whitespace),
    re.compile(new_line),
    re.compile(whitespace),
)


# the model to use
model = "gpt-4"
# token calculator
enc = tiktoken.encoding_for_model(model)


class Document:
    def __init__(self, text: str, span: tuple[int, int]):
        self.text = text
        self.span = span
        self.start = self.span[0]
        self.end = self.span[1]

    def __add__(self, other):
        return Document(text=self.text + other.text, span=(self.start, other.end))

    def __repr__(self):
        return f"{self.__class__.__qualname__}(span={self.span!r}, text={self.text!r})"


def calc_tokens(text):
    return len(enc.encode(text))


def merge_docs(docs: list[Document]) -> Document:
    ret = functools.reduce(operator.add, docs)
    ret.text = ret.text.strip()
    return ret


def text_splitter(
    docs: typing.Iterable[str | Document],
    *,
    chunk_size: int,
    length_function: typing.Callable[[str], int],
    separators: list[re.Pattern] = default_separators,
) -> list[Document]:
    if not docs:
        return []
    if isinstance(docs, str):
        docs = [docs]
    if isinstance(docs[0], str):
        docs = [Document(d, (idx, idx)) for idx, d in enumerate(docs)]
    return list(
        _join(
            _split(docs, chunk_size, length_function, separators),
            chunk_size,
        )
    )


def _split(
    docs: list[Document],
    chunk_size: int,
    length_function: typing.Callable[[str], int],
    separators: list[re.Pattern],
) -> typing.Iterable[tuple[Document, int]]:
    if not separators:
        raise ValueError("No separators left, cannot split further")
    for doc in docs:
        # skip empty docs
        if not doc.text.strip():
            continue
        # if the doc is small enough, no need to split
        doc_len = length_function(doc.text)
        if doc_len <= chunk_size:
            yield doc, doc_len
            continue
        for text in re_split(separators[0], doc.text):
            # skip empty fragments
            if not text.strip():
                continue
            frag = Document(text, doc.span)
            frag_len = length_function(text)
            # if the fragment is small enough, no need for further splitting
            if frag_len <= chunk_size:
                yield frag, frag_len
            else:
                yield from _split([frag], chunk_size, length_function, separators[1:])


def re_split(pat: re.Pattern, text: str):
    """Similar to re.split, but preserves the matched groups after splitting"""
    last_match_end = 0
    for match in pat.finditer(text):
        end_char = "".join(match.groups())
        frag = text[last_match_end : match.start()] + end_char
        if frag:
            yield frag
        last_match_end = match.end()
    yield text[last_match_end:]


def _join(
    docs: typing.Iterable[tuple[Document, int]], chunk_size: int
) -> typing.Iterator[Document]:
    window = []
    window_len = 0
    for doc, doc_len in docs:
        # grow window until largest possible chunk
        if window_len + doc_len <= chunk_size:
            window.append(doc)
            window_len += doc_len
        # reset window
        else:
            # return the window until now
            if window:
                yield merge_docs(window)
            window = [doc]
            window_len = doc_len
    # return the leftover
    if window:
        yield merge_docs(window)
