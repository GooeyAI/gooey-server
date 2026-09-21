import React from "react";
import Tippy, { useSingleton } from "@tippyjs/react";
import { RenderedMarkdown } from "~/renderedMarkdown";

export type TooltipPlacement = "left" | "right" | "top" | "bottom" | "auto";

export function GooeyHelpIcon({
  content,
  placement,
}: {
  content: string;
  placement?: TooltipPlacement;
}) {
  return (
    <GooeyTooltip content={content} placement={placement}>
      <i role="button" className="fa-regular fa-circle-info text-muted ms-1" />
    </GooeyTooltip>
  );
}

export function GooeyTooltip({
  content,
  children,
  placement,
  fitContent = false,
}: {
  content: string;
  children: React.ReactElement;
  placement?: TooltipPlacement;
  fitContent?: boolean;
}) {
  const [source, target] = useSingleton({
    overrides: ["placement", "theme"],
  });
  let theme: string | undefined;
  if (fitContent) {
    theme = "gooey-fit-content";
  }
  return (
    <>
      <Tippy
        singleton={source}
        animation={"scale"}
        duration={80}
        /* [show, hide]. A bare number delays both, which left the tooltip on screen for
           1.2s after the pointer had gone; leaving is not something to wait out. */
        delay={[1200, 0]}
        interactive
        /* A tap fires `mouseenter` and never `mouseleave`, so on a phone a tooltip opens
           and has nothing to close it - and the control it named is often gone by then. */
        touch={false}
        /* Tippy defaults to appending the popper to the reference's own parent, which put
           it inside whatever laid that reference out - a flex row, in every caller here -
           where it became a flex item and collapsed to 0x0. It mounted and never showed. */
        appendTo={() => document.body}
      />
      <Tippy
        singleton={target}
        placement={placement || "auto"}
        theme={theme}
        content={
          <div className="bg-dark p-2 b-1 shadow rounded container-margin-reset gooey-tooltip-box">
            <RenderedMarkdown body={content} />
          </div>
        }
      >
        {children}
      </Tippy>
    </>
  );
}
