import pytest
from daras_ai.text_format import wa_markdown

WHATSAPP_MARKDOWN_TEST = [
    (
        """# This is an <h1>\n## This is an <h2>\n### This is an <h3>\n#### This is an <h4>\n##### This is an <h5>\n###### This is an <h6>""",
        """*This is an <h1>*\n\n*This is an <h2>*\n\n*This is an <h3>*\n\n*This is an <h4>*\n\n*This is an <h5>*\n\n*This is an <h6>*\n""",
    ),
    (
        """This is an h1\n=============\n\nThis is an h2\n-------------""",
        """*This is an h1*\n\n*This is an h2*\n""",
    ),
    (
        """*This text is in italics.*\n_And so is this text._\n\n**This text is in bold.**\n__And so is this text.__\n\n***This text is in both.***\n**_As is this!_**\n*__And this!__*""",
        """_This text is in italics._\n_And so is this text._\n\n*This text is in bold.*\n*And so is this text.*\n\n_*This text is in both.*_\n*_As is this!_*\n_*And this!*_\n""",
    ),
    (
        """~~This text is rendered with strikethrough.~~\n~This text is also rendered with strikethrough.~""",
        """~This text is rendered with strikethrough.~\n~This text is also rendered with strikethrough.~\n""",
    ),
    (
        """This is a paragraph. I'm typing in a paragraph isn't this fun?\n\nNow I'm in paragraph 2.\nI'm still in paragraph 2 too!\n\n\nI'm in paragraph three!\n\n\n\nI'm in paragraph four!""",
        """This is a paragraph. I'm typing in a paragraph isn't this fun?\n\nNow I'm in paragraph 2.\nI'm still in paragraph 2 too!\n\nI'm in paragraph three!\n\nI'm in paragraph four!\n""",
    ),
    (
        """> This is a block quote. You can either\n> manually wrap your lines and put a `>` before every line or you can let your lines get really long and wrap on their own.\n> It doesn't make a difference so long as they start with a `>`.""",
        """> This is a block quote. You can either\n> manually wrap your lines and put a `>` before every line or you can let your lines get really long and wrap on their own.\n> It doesn't make a difference so long as they start with a `>`.\n""",
    ),
    (
        """* Item\n* Item\n* Another item\n\nor\n\n+ Item\n+ Item\n+ One more item\n\nor\n\n- Item\n- Item\n- One last item""",
        """- Item\n- Item\n- Another item\n\nor\n\n- Item\n- Item\n- One more item\n\nor\n\n- Item\n- Item\n- One last item\n""",
    ),
    (
        """1. Item 1\n2. Item 2\n3. Item 3\n    1. Item 3a\n    2. Item 3b""",
        """1. Item 1\n2. Item 2\n3. Item 3\n   1. Item 3a\n   2. Item 3b\n""",
    ),
    (
        """    This is code\n    So is this\n    \n        my_array.each do |item|\n      puts item\n    end""",
        """```\nThis is code\nSo is this\n\n    my_array.each do |item|\n  puts item\nend\n```\n""",
    ),
    (
        """[Click me!](http://test.com/)\n[Click me!](http://test.com/ "Link to Test.com")\n[Go to music](/music/).\n\n[Click this link][link1] for more info about it!\n[Also check out this link][foobar] if you want to.\n\n[link1]: http://test.com/ \'Cool!\'\n[foobar]: http://foobar.biz/ \'Alright!\'""",
        """Click me! (http://test.com/)\nClick me! (http://test.com/)\nGo to music (/music/).\n\nClick this link (http://test.com/) for more info about it!\nAlso check out this link (http://foobar.biz/) if you want to.\n""",
    ),
    (
        """![This is the alt-attribute for my image](http://imgur.com/myimage.jpg "An optional title")\n        ![This is the alt-attribute.][myimage]\n\n[myimage]: relative/urls/cool/image.jpg "if you need a title, it\'s here"\n""",
        """This is the alt-attribute for my image (http://imgur.com/myimage.jpg "An optional title")\nThis is the alt-attribute. (relative/urls/cool/image.jpg "if you need a title, it\'s here")\n""",
    ),
    (
        """| Col1         | Col2     | Col3          |
| :----------- | :------: | ------------: |
| Left-aligned | Centered | Right-aligned |
| blah         | blah     | blah          |""",
        """| Col1 | Col2 | Col3 |
| :----------- | :------: | ------------: |
| Left-aligned | Centered | Right-aligned |
| blah | blah | blah |
""",
    ),
]


@pytest.mark.parametrize("text, expected", WHATSAPP_MARKDOWN_TEST)
def test_wa_markdown(text, expected):
    _, result = wa_markdown(text)
    assert result == expected
