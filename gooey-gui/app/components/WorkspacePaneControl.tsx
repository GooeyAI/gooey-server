import "./RecipeWorkspace/RecipeWorkspace.css";

import clsx from "clsx";
import type { WorkspacePaneControlProps } from "@gooey-types/recipe_workspace_props";
import { GooeyTooltip } from "./GooeyTooltip";

/** Field docs live on the python model. `Partial` because RecipeWorkspace renders its own
 * controls in React with only a label and a handler, while python sends the full set. */
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
  /** React call sites act directly; python ones pass `event_name` instead. */
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

  // Contains the visible label (WCAG 2.5.3), plus the action when a tooltip names one.
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

  // A labelled control needs no tooltip repeating its label; an explicit one still shows.
  if (show_label && !tooltip) return button;

  return (
    <GooeyTooltip content={tooltip || label} placement="bottom" fitContent>
      {button}
    </GooeyTooltip>
  );
}
