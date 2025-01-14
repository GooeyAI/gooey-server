import markdown_it.renderer


class RendererWhatsApp(markdown_it.renderer.RendererProtocol):
    __output__ = "WhatsApp"

    def __init__(self, parser=None):
        self.collected_img_urls = []

        self.heading_open = self.strong_open
        self.heading_close = self.strong_close

        self.fence = self.code_block

    def render(self, tokens, options, env):
        result = ""
        for i, token in enumerate(tokens):
            if token.type == "inline":
                if token.children:
                    result += self.render(token.children, options, env)
            else:
                render_fn = getattr(self, token.type, None)
                if render_fn:
                    result += render_fn(token)
                else:
                    result += token.content
        return result

    # whatsapp only allows 1 star for bolding
    _strong_level = 0

    def strong_open(self, token):
        self._strong_level += 1
        if self._strong_level == 1:
            return "*"
        else:
            return ""

    def strong_close(self, token):
        self._strong_level -= 1
        if self._strong_level == 0:
            return "*"
        else:
            return ""

    def em_open(self, token):
        return "_"

    def em_close(self, token):
        return "_"

    def s_open(self, token):
        return "~"

    def s_close(self, token):
        return "~"

    def blockquote_open(self, token):
        return "> "

    def code_inline(self, token):
        return f"`{token.content}`"

    def code_block(self, token):
        return "```"

    def list_item_open(self, token):
        if token.info:
            return f"{token.info}. "
        else:
            return "- "

    current_link = None

    def link_open(self, token):
        self.current_link = token.attrs.get("href")
        return ""

    def link_close(self, token):
        if self.current_link:
            return f" ({self.current_link})"
        return ""

    def image(self, token):
        url = token.attrs.get("src")
        if url and url.startswith("http"):  # ignore local images
            self.collected_img_urls.append(url)
        return ""
