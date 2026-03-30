from html import escape

import markdown_it
import markdown_it.renderer


class RendererTelegramHTML(markdown_it.renderer.RendererProtocol):
    __output__ = "TelegramHTML"

    def __init__(self, parser=None):
        self.parser = parser
        self._reset_state()
        self._list_level = 0
        self._list_type_stack: list[str] = []
        self._ordered_list_number_stack: list[int] = []
        self._link_href: str | None = None
        self.fence = self.code_block

    def _reset_state(self):
        self._list_level = 0
        self._list_type_stack = []
        self._ordered_list_number_stack = []
        self._link_href = None
        self._table_headers: list[str] = []
        self._table_rows: list[list[str]] = []
        self._table_current_row: list[str] | None = None
        self._table_current_cell: list[str] | None = None
        self._table_in_header = False

    def _in_table_cell(self) -> bool:
        return self._table_current_cell is not None

    def _append_table_cell_text(self, text: str):
        if self._table_current_cell is not None:
            self._table_current_cell.append(text)

    def _render_tokens(self, tokens, options, env):
        result = ""
        for token in tokens:
            if token.type == "inline":
                if token.children:
                    result += self._render_tokens(token.children, options, env)
                continue
            render_fn = getattr(self, token.type, None)
            if render_fn:
                result += render_fn(token)
            elif token.content:
                if self._in_table_cell():
                    self._append_table_cell_text(token.content)
                else:
                    result += escape(token.content)
        return result

    def render(self, tokens, options, env):
        self._reset_state()
        return self._render_tokens(tokens, options, env)

    def _render_table(self) -> str:
        headers = [cell.strip() for cell in self._table_headers]
        rows = [[cell.strip() for cell in row] for row in self._table_rows]
        if not headers and not rows:
            return ""
        column_count = max(len(headers), *(len(row) for row in rows), 0)
        if column_count == 0:
            return ""
        widths = [0] * column_count
        for i, cell in enumerate(headers):
            widths[i] = max(widths[i], len(cell))
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        def render_row(cells: list[str]) -> str:
            padded = []
            for i in range(column_count):
                padded.append((cells[i] if i < len(cells) else "").ljust(widths[i]))
            return "| " + " | ".join(padded) + " |"

        lines: list[str] = []
        if headers:
            lines.append(render_row(headers))
            lines.append(
                "| " + " | ".join("-" * max(3, width) for width in widths) + " |"
            )
        for row in rows:
            lines.append(render_row(row))
        if not lines:
            return ""
        return f"<pre><code>{escape(chr(10).join(lines))}</code></pre>\n\n"

    def text(self, token):
        if self._in_table_cell():
            self._append_table_cell_text(token.content or "")
            return ""
        return escape(token.content)

    def html_inline(self, token):
        if self._in_table_cell():
            self._append_table_cell_text(token.content or "")
            return ""
        return escape(token.content)

    def html_block(self, token):
        if self._in_table_cell():
            self._append_table_cell_text(token.content or "")
            return ""
        return escape(token.content)

    def paragraph_open(self, token):
        return ""

    def paragraph_close(self, token):
        if self._list_level > 0:
            return ""
        return "\n\n"

    def heading_open(self, token):
        return "<b>"

    def heading_close(self, token):
        return "</b>\n\n"

    def strong_open(self, token):
        if self._in_table_cell():
            return ""
        return "<b>"

    def strong_close(self, token):
        if self._in_table_cell():
            return ""
        return "</b>"

    def em_open(self, token):
        if self._in_table_cell():
            return ""
        return "<i>"

    def em_close(self, token):
        if self._in_table_cell():
            return ""
        return "</i>"

    def s_open(self, token):
        if self._in_table_cell():
            return ""
        return "<s>"

    def s_close(self, token):
        if self._in_table_cell():
            return ""
        return "</s>"

    def code_inline(self, token):
        if self._in_table_cell():
            self._append_table_cell_text(token.content or "")
            return ""
        return f"<code>{escape(token.content)}</code>"

    def code_block(self, token):
        return f"<pre><code>{escape(token.content)}</code></pre>\n\n"

    def bullet_list_open(self, token):
        prefix = "\n" if self._list_level > 0 else ""
        self._list_level += 1
        self._list_type_stack.append("bullet")
        return prefix

    def bullet_list_close(self, token):
        if self._list_level > 0:
            self._list_level -= 1
        if self._list_type_stack:
            self._list_type_stack.pop()
        return "\n" if self._list_level == 0 else ""

    def ordered_list_open(self, token):
        prefix = "\n" if self._list_level > 0 else ""
        self._list_level += 1
        self._list_type_stack.append("ordered")
        self._ordered_list_number_stack.append(int(token.attrGet("start") or 1))
        return prefix

    def ordered_list_close(self, token):
        if self._list_level > 0:
            self._list_level -= 1
        if self._list_type_stack:
            self._list_type_stack.pop()
        if self._ordered_list_number_stack:
            self._ordered_list_number_stack.pop()
        return "\n" if self._list_level == 0 else ""

    def list_item_open(self, token):
        if not self._list_type_stack:
            return ""
        indent = "  " * max(self._list_level - 1, 0)
        list_type = self._list_type_stack[-1]
        if list_type == "ordered":
            number = self._ordered_list_number_stack[-1]
            self._ordered_list_number_stack[-1] += 1
            return f"{indent}{number}. "
        return f"{indent}• "

    def list_item_close(self, token):
        return "\n"

    def softbreak(self, token):
        if self._in_table_cell():
            self._append_table_cell_text(" ")
            return ""
        return "\n"

    def hardbreak(self, token):
        if self._in_table_cell():
            self._append_table_cell_text(" ")
            return ""
        return "\n"

    def blockquote_open(self, token):
        return "<blockquote>"

    def blockquote_close(self, token):
        return "</blockquote>\n\n"

    def link_open(self, token):
        if self._in_table_cell():
            return ""
        self._link_href = escape(token.attrGet("href") or "", quote=True)
        return f'<a href="{self._link_href}">'

    def link_close(self, token):
        if self._in_table_cell():
            return ""
        self._link_href = None
        return "</a>"

    def image(self, token):
        if self._in_table_cell():
            self._append_table_cell_text(token.content or "")
            return ""
        alt = escape(token.content or "")
        src = escape(token.attrGet("src") or "", quote=True)
        return f"{alt} ({src})" if src else alt

    def hr(self, token):
        return "───\n\n"

    def spoiler_open(self, token):
        if self._in_table_cell():
            return ""
        return "<tg-spoiler>"

    def spoiler_close(self, token):
        if self._in_table_cell():
            return ""
        return "</tg-spoiler>"

    def table_open(self, token):
        self._table_headers = []
        self._table_rows = []
        self._table_current_row = None
        self._table_current_cell = None
        self._table_in_header = False
        return ""

    def table_close(self, token):
        html = self._render_table()
        self._table_headers = []
        self._table_rows = []
        self._table_current_row = None
        self._table_current_cell = None
        self._table_in_header = False
        return html

    def thead_open(self, token):
        self._table_in_header = True
        return ""

    def thead_close(self, token):
        self._table_in_header = False
        return ""

    def tbody_open(self, token):
        return ""

    def tbody_close(self, token):
        return ""

    def tr_open(self, token):
        self._table_current_row = []
        return ""

    def tr_close(self, token):
        if self._table_current_row is None:
            return ""
        if self._table_in_header:
            self._table_headers = self._table_current_row
        else:
            self._table_rows.append(self._table_current_row)
        self._table_current_row = None
        return ""

    def th_open(self, token):
        self._table_current_cell = []
        return ""

    def th_close(self, token):
        if self._table_current_row is not None and self._table_current_cell is not None:
            self._table_current_row.append("".join(self._table_current_cell))
        self._table_current_cell = None
        return ""

    def td_open(self, token):
        self._table_current_cell = []
        return ""

    def td_close(self, token):
        if self._table_current_row is not None and self._table_current_cell is not None:
            self._table_current_row.append("".join(self._table_current_cell))
        self._table_current_cell = None
        return ""


_telegram_html_md = markdown_it.MarkdownIt(
    "commonmark",
    {
        "html": False,
        "linkify": True,
        "breaks": False,
        "typographer": False,
    },
    renderer_cls=RendererTelegramHTML,
)
_telegram_html_md.enable("strikethrough")
_telegram_html_md.enable("table")


def markdown_to_telegram_html(text: str) -> str:
    return _telegram_html_md.render(text).rstrip("\n")
