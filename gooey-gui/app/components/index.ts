import type { OnChange } from "~/app";
import type { TreeNode } from "~/renderer";

export type CustomComponentProps = {
  children: Array<TreeNode>;
  onChange: OnChange;
  state: Record<string, any>;
};

export * from "./WorkspaceMemoryTable";
export * from "./bulkProgress/BulkProgressCard";
export * from "./ComposioAuthRequired";
export * from "./AskGooeyNew";
export * from "./ForgotPasswordForm";
export * from "./GooeyBuilderInlineEmbed";
export * from "./GooeyEmbedTeardown";
export * from "./GooeyPopover";
export * from "./HistoryPage";
export * from "./HomePage";
export * from "./InsufficientCredits";
export * from "./LoginForm";
export * from "./PaymentRequired";
export * from "./RunGrid";
export * from "./NavigationSidebar";
export * from "./RecipeTopBar";
export * from "./RecipeWorkspace";
export * from "./Sidebar";
export * from "./ToolPage";
export * from "./WorkspacePaneControl";
