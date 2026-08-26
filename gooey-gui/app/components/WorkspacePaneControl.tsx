import "./RecipeWorkspace/RecipeWorkspace.css";

import clsx from "clsx";
import type { WorkspacePaneControlProps } from "@gooey-types/recipe_workspace_props";
import { GooeyTooltip } from "./GooeyTooltip";

/** Field docs live on the python model this is generated from - see
 * `gooey_gui/types/recipe_workspace_props.py`.
 *
 * `Partial` because this control has two callers with different needs: python sends the
 * full prop set through the render tree, while RecipeWorkspace renders its own pane-pairing
 * controls in React and passes a handler plus a label and nothing else. Every field name is
 * still checked against the model, so renaming one there breaks the build here.
 */
export function WorkspacePaneControl({
  label,
  tooltip,
  icon,
  photo_url,
  show_label,
  onClick,
  event_name,
  className,
}: Partial<WorkspacePaneControlProps> & {
  label: string;
  /** React call sites dispatch nothing - they act directly. Python call sites pass
   * `event_name` instead, because they have no handler to hand across the boundary. */
  onClick?: () => void;
}) {
  const handleClick = () => {
    if (onClick) {
      onClick();
      return;
    }
    if (event_name) {
      window.dispatchEvent(new Event(event_name));
    }
  };

  // The accessible name still contains the visible label - WCAG 2.5.3 requires that - but
  // picks up the action when a tooltip adds one, so a screen reader hears what the click does
  // and not just what the surface is called.
  const accessibleName =
    show_label && tooltip ? `${label}: ${tooltip}` : tooltip || label;

  const button = (
    <button
      type="button"
      className={clsx(
        "v2-pane-control",
        show_label && "v2-pane-control-labelled",
        className
      )}
      onClick={handleClick}
      aria-label={accessibleName}
    >
      {photo_url ? (
        <img className="v2-pane-control-photo" src={photo_url} alt="" />
      ) : (
        <i className={icon} />
      )}
      {show_label && <span className="v2-pane-control-label">{label}</span>}
    </button>
  );

  // A tooltip that only repeats a label already on screen is noise, so the labelled form drops
  // it - unless given an explicit `tooltip`, which by definition says something the label does
  // not. `aria-label` supplies the accessible name either way.
  if (show_label && !tooltip) return button;

  return (
    <GooeyTooltip content={tooltip || label} placement="bottom" fitContent>
      {button}
    </GooeyTooltip>
  );
}
