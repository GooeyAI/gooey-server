import Tippy from "@tippyjs/react";
import { useState } from "react";
import type { CustomComponentProps } from "~/components";
import type { TreeNode } from "~/renderer";
import { RenderedChildren } from "~/renderer";
import { TooltipPlacement } from "./GooeyTooltip";

export function GooeyPopover({
  content,
  children,
  onChange,
  state,
  placement,
  ...props
}: CustomComponentProps & {
  content: Array<TreeNode>;
  placement?: TooltipPlacement;
}) {
  const [visible, setVisible] = useState(false);

  return (
    <Tippy
      visible={visible}
      onClickOutside={() => setVisible(false)}
      maxWidth={"90vw"}
      content={
        <div onClick={() => setVisible(false)}>
          <RenderedChildren
            children={content}
            onChange={onChange}
            state={state}
          />
        </div>
      }
      animation="scale"
      duration={100}
      placement={placement || "auto"}
      {...props}
    >
      <button type="button" onClick={() => setVisible(!visible)}>
        <RenderedChildren
          children={children}
          onChange={onChange}
          state={state}
        />
      </button>
    </Tippy>
  );
}
