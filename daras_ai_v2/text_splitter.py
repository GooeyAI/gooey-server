import functools
import operator
import re
import threading
import typing
from enum import Enum

import tiktoken
from collections import deque

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

threadlocal = threading.local()


def default_length_function(text: str) -> int:
    try:
        enc = threadlocal.enc
    except AttributeError:
        enc = tiktoken.encoding_for_model("gpt-4")
        threadlocal.enc = enc
    return len(enc.encode(text))


L = typing.Callable[[str], int]


class Document:
    _length: int | None = None

    def __init__(
        self,
        text: str,
        span: tuple[int, int],
        length_function: L = default_length_function,
        **kwargs,
    ):
        self.text = text
        self.span = span
        self.start = self.span[0]
        self.end = self.span[1]
        self.length_function = length_function
        self.kwargs = kwargs

    def __len__(self):
        if self._length is None:
            self._length = self.length_function(self.text)
        return self._length

    def __add__(self, other):
        return Document(
            text=self.text + other.text,
            span=(self.start, other.end),
            length_function=self.length_function,
        )

    def __repr__(self):
        return f"{self.__class__.__qualname__}(span={self.span!r}, text={self.text!r})"


class SeparatorFallback(Enum):
    IGNORE = 1
    RAISE_ERROR = 2


def text_splitter(
    docs: typing.Iterable[str | Document],
    *,
    chunk_size: int,
    chunk_overlap: int = 0,
    separators: list[re.Pattern] = default_separators,
    fallback: SeparatorFallback = SeparatorFallback.IGNORE,
    length_function: L = default_length_function,
) -> list[Document]:
    if not docs:
        return []
    if isinstance(docs, str):
        docs = [docs]
    if isinstance(docs[0], str):
        docs = [Document(d, (idx, idx), length_function) for idx, d in enumerate(docs)]
    splits = _split(docs, chunk_size, separators, fallback)
    docs = list(_join(splits, chunk_size, chunk_overlap))
    return docs


def _split(
    docs: list[Document],
    chunk_size: int,
    separators: list[re.Pattern],
    fallback: SeparatorFallback,
) -> typing.Iterable[Document]:
    if not separators:
        match fallback:
            case SeparatorFallback.IGNORE:
                return
            case SeparatorFallback.RAISE_ERROR:
                raise ValueError("No separators left, cannot split further")
    for doc in docs:
        # skip empty docs
        if not doc.text.strip():
            continue
        # if the doc is small enough, no need to split
        if len(doc) <= chunk_size:
            yield doc
            continue
        for text in re_split(separators[0], doc.text):
            # skip empty fragments
            if not text.strip():
                continue
            frag = Document(text, doc.span, doc.length_function)
            # if the fragment is small enough, no need for further splitting
            if len(frag) <= chunk_size:
                yield frag
            else:
                yield from _split([frag], chunk_size, separators[1:], fallback)


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
    docs: typing.Iterable[Document],
    chunk_size: int,
    chunk_overlap: int,
) -> typing.Iterator[Document]:
    window = deque()
    window_len = 0
    for doc in docs:
        # grow window until largest possible chunk
        if window_len + len(doc) <= chunk_size:
            window.append(doc)
            window_len += len(doc)
        else:
            # return the window until now
            if window:
                yield _merge(window)
            # reset window
            prev_window = window
            window = deque([doc])
            window_len = len(doc)
            # add overlap from previous window
            overlap_len = 0
            for chunk in reversed(prev_window):
                if (
                    # check if overlap is too large
                    overlap_len + len(chunk) > chunk_overlap
                    # check if window is too large
                    or window_len + len(chunk) > chunk_size
                ):
                    break
                window.appendleft(chunk)
                overlap_len += len(chunk)
                window_len += len(chunk)
    # return the leftover
    if window:
        yield _merge(window)


def _merge(docs: typing.Iterable[Document]) -> Document:
    ret = functools.reduce(operator.add, docs)
    return Document(
        text=ret.text.strip(),  # remove whitespace after merge
        span=ret.span,
        length_function=ret.length_function,
    )
