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
}: {
  content: string;
  children: React.ReactElement;
  placement?: TooltipPlacement;
}) {
  const [source, target] = useSingleton({
    overrides: ["placement"],
  });
  return (
    <>
      <Tippy
        singleton={source}
        animation={"scale"}
        duration={80}
        delay={100}
        interactive
      />
      <Tippy
        singleton={target}
        placement={placement || "auto"}
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
