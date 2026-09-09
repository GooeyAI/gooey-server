from daras_ai_v2.bots import parse_bot_html
from daras_ai_v2.csv_lines import csv_decode_row
from daras_ai_v2.facebook_bots import _build_interactive_list_msg
from daras_ai_v2.language_model import is_llm_chunk_large_enough


def test_buttons_unchanged():
    buttons, text, thinking, disable_feedback = parse_bot_html(
        "Hi there\n"
        '<button gui-target="input_prompt" gui-description="Full question?">📝 Guide</button>\n'
        '<button gui-action="disable_feedback">✅ I Agree</button>'
    )
    assert text.strip() == "Hi there"
    assert disable_feedback
    assert [b["title"] for b in buttons] == ["📝 Guide", "✅ I Agree"]
    assert buttons[0]["description"] == "Full question?"
    assert "description" not in buttons[1]
    assert csv_decode_row(buttons[0]["id"]) == ["1", "input_prompt", "📝 Guide"]
    assert csv_decode_row(buttons[1]["id"]) == [
        "2",
        "input_prompt",
        "disable_feedback",
        "✅ I Agree",
    ]


def test_select_options():
    buttons, text, thinking, disable_feedback = parse_bot_html(
        "Pick a car\n"
        '<select name="cars" gui-target="input_prompt">\n'
        '  <option gui-description="Tell me about Volvo" value="volvo">Volvo</option>\n'
        '  <option gui-target="input_images" value="saab">Saab</option>\n'
        "  <option>Audi</option>\n"
        "</select>"
    )
    assert text.strip() == "Pick a car"
    assert not disable_feedback
    assert [b["title"] for b in buttons] == ["Volvo", "Saab", "Audi"]
    assert buttons[0]["description"] == "Tell me about Volvo"
    assert "description" not in buttons[1]
    # value is what gets sent, label is what gets shown
    assert csv_decode_row(buttons[0]["id"]) == ["1", "input_prompt", "volvo"]
    # option's own gui-target wins over the select's
    assert csv_decode_row(buttons[1]["id"]) == ["2", "input_images", "saab"]
    # no value falls back to the label
    assert csv_decode_row(buttons[2]["id"]) == ["3", "input_prompt", "Audi"]


def test_select_inherits_action_and_mixes_with_buttons():
    buttons, text, thinking, disable_feedback = parse_bot_html(
        "<button>First</button>\n"
        '<select gui-action="disable_feedback"><option value="b">Second</option></select>\n'
        "<button>Third</button>"
    )
    assert text.strip() == ""
    assert disable_feedback
    assert [b["title"] for b in buttons] == ["First", "Second", "Third"]
    assert [csv_decode_row(b["id"])[0] for b in buttons] == ["1", "2", "3"]


def test_streaming_waits_for_select_to_close():
    partial = "Pick a car\n<select><option value='a'>A</option>"
    assert not is_llm_chunk_large_enough({"chunk": partial, "content": ""}, 5)
    complete = partial + "</select>\nDone.\n"
    assert is_llm_chunk_large_enough({"chunk": complete, "content": ""}, 5)


def test_wrapping_label_becomes_section():
    buttons, text, *_ = parse_bot_html(
        "Some answer\n"
        "<label>Follow up questions\n"
        '<select gui-target="input_prompt">'
        '<option value="a">A</option><option value="b">B</option>'
        "</select></label>\n"
        "<button>Other</button>"
    )
    assert text.strip() == "Some answer"
    assert [b["title"] for b in buttons] == ["A", "B", "Other"]
    assert [b.get("section") for b in buttons] == ["Follow up questions"] * 2 + [None]


def test_wa_list_groups_rows_by_section():
    buttons = [
        {"id": "1", "title": "A", "section": "Cars"},
        {"id": "2", "title": "B", "section": "Cars"},
        {"id": "3", "title": "C"},
        {"id": "4", "title": "D", "section": "Bikes"},
    ]
    sections = _build_interactive_list_msg(buttons, "hi")["interactive"]["action"][
        "sections"
    ]
    assert [s["title"] for s in sections] == ["Cars", "Options", "Bikes"]
    assert [[r["title"] for r in s["rows"]] for s in sections] == [
        ["A", "B"],
        ["C"],
        ["D"],
    ]


def test_wa_list_single_untitled_section():
    msg = _build_interactive_list_msg([{"id": "1", "title": "A"}], "hi")
    assert msg["interactive"]["action"]["sections"] == [
        {"rows": [{"id": "1", "title": "A"}]}
    ]
