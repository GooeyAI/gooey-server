import type { SurfaceId } from "@gooey-types/recipe_workspace_props";
import type { TreeNode } from "../../renderer";

export function namedSurfaceSlots(
  children: TreeNode[]
): Record<SurfaceId, TreeNode> {
  const surfaces = {} as Partial<Record<SurfaceId, TreeNode>>;
  for (const child of children) {
    if (child.name !== "RecipeSurface") {
      throw new Error(
        `RecipeWorkspace child must be RecipeSurface, got ${child.name}`
      );
    }
    if (child.children.length !== 1) {
      throw new Error("RecipeSurface must contain exactly one slot node");
    }
    const surface = child.props.surface as SurfaceId;
    if (surfaces[surface]) {
      throw new Error(`RecipeWorkspace received duplicate ${surface} surface`);
    }
    surfaces[surface] = child.children[0];
  }
  for (const surface of ["about", "editor", "preview"] as const) {
    if (!surfaces[surface]) {
      throw new Error(`RecipeWorkspace is missing ${surface} surface`);
    }
  }
  return surfaces as Record<SurfaceId, TreeNode>;
}
