import type { ComponentProps, ComponentType } from "react";
import type { RecipeTopBarProps } from "@gooey-types/recipe_top_bar_props";
import type {
  RecipeSurfaceProps,
  RecipeWorkspaceProps,
  RecipeWorkspaceTriggerProps,
  WorkspacePaneControlProps,
} from "@gooey-types/recipe_workspace_props";
import type { SidebarProps } from "@gooey-types/sidebar_props";

import { AskGooeyNew } from "./components/AskGooeyNew";
import { BulkProgressCard } from "./components/bulkProgress/BulkProgressCard";
import { ComposioAuthRequired } from "./components/ComposioAuthRequired";
import { ForgotPasswordForm } from "./components/ForgotPasswordForm";
import { GooeyBuilderInlineEmbed } from "./components/GooeyBuilderInlineEmbed";
import { GooeyEmbedPreview } from "./components/GooeyEmbedPreview";
import { GooeyPopover } from "./components/GooeyPopover";
import { HistoryPage } from "./components/HistoryPage";
import { HomePage } from "./components/HomePage";
import { InsufficientCredits } from "./components/InsufficientCredits";
import { LoginForm } from "./components/LoginForm";
import { NavigationSidebar } from "./components/NavigationSidebar";
import { PaymentRequired } from "./components/PaymentRequired";
import { RecipeTopBar } from "./components/RecipeTopBar";
import { RunGrid } from "./components/RunGrid";
import {
  RecipeSurface,
  RecipeWorkspace,
  RecipeWorkspaceTrigger,
} from "./components/RecipeWorkspace";
import { Sidebar } from "./components/Sidebar";
import { ToolPage } from "./components/ToolPage";
import { WorkspaceMemoryTable } from "./components/WorkspaceMemoryTable";
import { WorkspacePaneControl } from "./components/WorkspacePaneControl";
import type { CustomComponentProps } from "./components";

type DynamicComponent<Props> = ComponentType<CustomComponentProps & Props>;

const generatedV2Components = {
  RecipeSurface,
  RecipeTopBar,
  RecipeWorkspace,
  RecipeWorkspaceTrigger,
  Sidebar,
  WorkspacePaneControl,
} satisfies {
  RecipeSurface: DynamicComponent<RecipeSurfaceProps>;
  RecipeTopBar: DynamicComponent<RecipeTopBarProps>;
  RecipeWorkspace: DynamicComponent<RecipeWorkspaceProps>;
  RecipeWorkspaceTrigger: DynamicComponent<RecipeWorkspaceTriggerProps>;
  Sidebar: DynamicComponent<SidebarProps>;
  WorkspacePaneControl: DynamicComponent<WorkspacePaneControlProps>;
};

export const customComponentRegistry = {
  AskGooeyNew,
  BulkProgressCard,
  ComposioAuthRequired,
  ForgotPasswordForm,
  GooeyBuilderInlineEmbed,
  GooeyEmbedPreview,
  GooeyPopover,
  HistoryPage,
  HomePage,
  InsufficientCredits,
  LoginForm,
  NavigationSidebar,
  PaymentRequired,
  RunGrid,
  ...generatedV2Components,
  ToolPage,
  WorkspaceMemoryTable,
} as const;

export type CustomComponentName = keyof typeof customComponentRegistry;

export type CustomComponentServerProps = {
  [Name in CustomComponentName]: Omit<
    ComponentProps<(typeof customComponentRegistry)[Name]>,
    keyof CustomComponentProps
  >;
};

export function isCustomComponentName(
  name: string
): name is CustomComponentName {
  return name in customComponentRegistry;
}

export function getCustomComponent(name: CustomComponentName) {
  return customComponentRegistry[name] as ComponentType<
    CustomComponentProps & Record<string, unknown>
  >;
}
