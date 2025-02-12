from mdformat.renderer._context import (
    RenderContext,
    make_render_children,
    _render_inline_as_text,
    WRAP_POINT,
)
from mdformat.renderer._tree import RenderTreeNode
from mdformat.plugins import ParserExtensionInterface
from mdformat.renderer._util import maybe_add_link_brackets


def wa_heading_renderer(node: RenderTreeNode, context: RenderContext) -> str:
    text = make_render_children(separator="")(node, context)
    text = text.lstrip("*")
    text = text.rstrip("*")

    return "*" + text + "*"


def wa_em_renderer(node: RenderTreeNode, context: RenderContext) -> str:
    text = make_render_children(separator="")(node, context)
    return "_" + text + "_"


def wa_strong_renderer(node: RenderTreeNode, context: RenderContext) -> str:
    text = make_render_children(separator="")(node, context)
    return "*" + text + "*"


def wa_link_renderer(node: RenderTreeNode, context: RenderContext) -> str:
    if node.info == "auto":
        autolink_url = node.attrs["href"]
        # Remove 'mailto:' if the URL is a mailto link and the content doesn't start with 'mailto:'
        if autolink_url.startswith("mailto:") and not node.children[
            0
        ].content.startswith("mailto:"):
            autolink_url = autolink_url[7:]
        return f"{autolink_url}"

    # Get the display text for the link
    text = "".join(child.render(context) for child in node.children)

    uri = node.attrs["href"]
    return f"{text} ({uri})"


def wa_image_renderer(node: RenderTreeNode, context: RenderContext) -> str:
    description = _render_inline_as_text(node, context)
    ref_label = node.meta.get("label")
    if ref_label:
        context.env["used_refs"].add(ref_label)
        ref_label_repr = ref_label.lower()
        if description.lower() == ref_label_repr:
            return f"[{description}]"
        return f" {description} [{ref_label_repr}]"

    uri = node.attrs["src"]
    assert isinstance(uri, str)
    uri = maybe_add_link_brackets(uri)
    title = node.attrs.get("title")
    if title is not None:
        return f'{description} ({uri} "{title}")'
    return f"{description} ({uri})"


def wa_hr_renderer(node: RenderTreeNode, context: RenderContext) -> str:
    return ""


def wa_strikethrough_renderer(node: RenderTreeNode, context: RenderContext) -> str:
    # Render the content inside the strikethrough element
    text = make_render_children(separator="")(node, context)
    return f"~{text}~"


class WhatsappParser(ParserExtensionInterface):

    RENDERERS = {
        "heading": wa_heading_renderer,
        "em": wa_em_renderer,
        "strong": wa_strong_renderer,
        "link": wa_link_renderer,
        "hr": wa_hr_renderer,
        "image": wa_image_renderer,
        "s": wa_strikethrough_renderer,
    }
