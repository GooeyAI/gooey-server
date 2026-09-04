import type {
  MenuIntent,
  PublishIntent,
  RunIntent,
  ShareIntent,
  StopIntent,
} from "@gooey-types/recipe_top_bar_props";

export type RecipeSubmitIntent =
  | RunIntent
  | StopIntent
  | PublishIntent
  | ShareIntent
  | MenuIntent;

export function encodeSubmitIntent(intent: RecipeSubmitIntent): string {
  return JSON.stringify(intent);
}
