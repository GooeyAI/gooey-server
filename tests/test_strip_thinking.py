import pytest

from daras_ai_v2.bots import strip_thinking


@pytest.mark.parametrize("text", [None, "", "   \n  "])
def test_strip_thinking_empty(text):
    assert strip_thinking(text) == ""


def test_strip_thinking_no_thinking():
    text = "Hello **world**, visit https://gooey.ai/?a=1&b=2 <3"
    assert strip_thinking(text) == text


def test_strip_thinking_removes_block():
    assert (
        strip_thinking("<think>let me reason about this</think>\n\nThe answer is 42.")
        == "The answer is 42."
    )
    assert (
        strip_thinking("The answer is 42.\n\n<think>was that right?</think>")
        == "The answer is 42."
    )


def test_strip_thinking_multiline_and_multiple_blocks():
    text = """
<think>
first thought
second thought
</think>
Step one.
<think>more reasoning</think>
Step two.
""".strip()
    assert strip_thinking(text) == "Step one.\n\nStep two."


def test_strip_thinking_unterminated_block():
    # while streaming, the closing tag hasn't arrived yet
    assert strip_thinking("Thinking...\n<think>partial reason") == "Thinking..."
    assert strip_thinking("<think>partial reason") == ""


def test_strip_thinking_preserves_buttons():
    text = (
        '<button gui-target="input_prompt">Yes</button>'
        "<think>should i ask?</think>"
        '<button gui-action="disable_feedback">No</button>'
    )
    assert strip_thinking(text) == (
        '<button gui-target="input_prompt">Yes</button>'
        '<button gui-action="disable_feedback">No</button>'
    )


def test_strip_thinking_preserves_tag_order_with_text():
    text = (
        "<think>reasoning</think>"
        "Here are your options:\n"
        '<button gui-target="input_prompt">Alpha</button>\n'
        "or maybe\n"
        '<button gui-target="input_prompt">Beta</button>\n'
        "<b>Pick one</b> and <i>tell me</i> — <video src='x.mp4'/>"
    )
    assert strip_thinking(text) == (
        "Here are your options:\n"
        '<button gui-target="input_prompt">Alpha</button>\n'
        "or maybe\n"
        '<button gui-target="input_prompt">Beta</button>\n'
        "<b>Pick one</b> and <i>tell me</i> — <video src='x.mp4'/>"
    )


def test_strip_thinking_preserves_nested_markup_inside_kept_tags():
    text = "<p>outer <span>inner <think>hmm</think>text</span> tail</p>"
    assert strip_thinking(text) == "<p>outer <span>inner text</span> tail</p>"


def test_strip_thinking_tag_variants():
    assert strip_thinking('<think type="reasoning">x</think>y') == "y"
    assert strip_thinking("<THINK>x</THINK>y") == "y"
    assert strip_thinking("<think>x</think >y") == "y"
    # not a thinking tag
    assert strip_thinking("<thinking>x</thinking>") == "<thinking>x</thinking>"
    assert strip_thinking("I think that's right") == "I think that's right"


def test_strip_thinking_streaming_prefix_stays_stable():
    """
    Platforms that can't edit messages send `text[last_idx:]` deltas, so the
    stripped prefix must never change as more of the response streams in.
    """
    chunks = [
        "Hi there. ",
        "Hi there. <think>",
        "Hi there. <think>hmm",
        "Hi there. <think>hmm, let me check</think>",
        "Hi there. <think>hmm, let me check</think> The answer",
        "Hi there. <think>hmm, let me check</think> The answer is 42.",
    ]
    sent = ""
    for chunk in chunks:
        stripped = strip_thinking(chunk)
        assert stripped.startswith(sent), f"{stripped!r} does not extend {sent!r}"
        sent = stripped
    # the whitespace on either side of the removed block is left alone
    assert sent == "Hi there.  The answer is 42."
