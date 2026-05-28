import type { OnChange } from "~/app";
import type { TreeNode } from "~/renderer";

export type CustomComponentProps = {
  children: Array<TreeNode>;
  onChange: OnChange;
  state: Record<string, any>;
};

export * from "./ComposioAuthRequired";
export * from "./ExploreBuilderPrompt";
export * from "./GooeyBuilderInlineEmbed";
export * from "./GooeyPopover";
export * from "./InsufficientCredits";
export * from "./PaymentRequired";
export * from "./Sidebar";
