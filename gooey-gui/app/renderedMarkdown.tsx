import { marked } from "marked";
import { RenderedHTML } from "~/renderedHTML";
import type { TooltipPlacement } from "./components/GooeyTooltip";

export function RenderedMarkdown({
  body,
  lineClamp,
  help,
  tooltipPlacement,
  lineClampExpand,
  ...attrs
}: // allowUnsafeHTML,
{
  body: string;
  lineClamp?: number;
  help?: string;
  tooltipPlacement?: TooltipPlacement;
  [attr: string]: any;
  // allowUnsafeHTML?: boolean;
}) {
  if (!body) return <></>;
  let html = marked.parse(body, {
    gfm: true,
    headerIds: false,
    mangle: false,
    breaks: true,
  });

  return (
    <RenderedHTML
      key={body}
      body={html}
      lineClamp={lineClamp}
      lineClampExpand={lineClampExpand}
      className="gui-html-container gui-md-container"
      help={help}
      tooltipPlacement={tooltipPlacement}
      {...attrs}
    />
  );
}
