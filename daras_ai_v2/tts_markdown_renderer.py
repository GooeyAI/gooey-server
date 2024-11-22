from inspect import getmembers, ismethod

from html.parser import HTMLParser


class HTMLTextRenderer(HTMLParser):
    def __init__(self):
        super().__init__()
        self._handled_data = list()

    def handle_data(self, data):
        self._handled_data.append(data)

    def reset(self):
        self._handled_data = list()
        super().reset()

    def render(self, html):
        self.feed(html)
        rendered_data = "".join(self._handled_data)
        self.reset()
        return rendered_data


class RendererPlain:
    __output__ = "plain"

    def __init__(self, parser=None):
        self.parser = parser
        self.htmlparser = HTMLTextRenderer()
        self.rules = {
            func_name.replace("render_", ""): func
            for func_name, func in getmembers(self, predicate=ismethod)
            if func_name.startswith("render_")
        }
        self.list_level = 0
        self.list_type_stack = []
        self.ordered_list_number_stack = []

    def render(self, tokens, options, env):
        if options is None and self.parser is not None:
            options = self.parser.options
        result = ""
        for i, token in enumerate(tokens):
            rule = self.rules.get(token.type, self.render_default)
            result += rule(tokens, i, options, env)
            if token.children is not None:
                result += self.render(token.children, options, env)
        return result.strip()

    def render_default(self, tokens, i, options, env):
        return ""

    def render_bullet_list_open(self, tokens, i, options, env):
        self.list_level += 1
        self.list_type_stack.append("bullet")
        return ""

    def render_bullet_list_close(self, tokens, i, options, env):
        self.list_level -= 1
        self.list_type_stack.pop()
        return ""

    def render_ordered_list_open(self, tokens, i, options, env):
        self.list_level += 1
        self.list_type_stack.append("ordered")
        self.ordered_list_number_stack.append(1)
        return ""

    def render_ordered_list_close(self, tokens, i, options, env):
        self.list_level -= 1
        self.list_type_stack.pop()
        self.ordered_list_number_stack.pop()
        return ""

    def render_list_item_open(self, tokens, i, options, env):
        indent = "    " * (self.list_level - 1)
        list_type = self.list_type_stack[-1]
        if list_type == "ordered":
            number = self.ordered_list_number_stack[-1]
            self.ordered_list_number_stack[-1] += 1
            return f"{indent}{number}. "
        else:
            return f"{indent}- "

    def render_list_item_close(self, tokens, i, options, env):
        return "\n"

    def render_paragraph_open(self, tokens, i, options, env):
        return ""

    def render_paragraph_close(self, tokens, i, options, env):
        return "\n"

    def render_text(self, tokens, i, options, env):
        return tokens[i].content

    def render_softbreak(self, tokens, i, options, env):
        return "\n"

    def render_hardbreak(self, tokens, i, options, env):
        return "\n"
