import "./RecipeWorkspace/RecipeWorkspace.css";

import clsx from "clsx";
import { GooeyTooltip } from "./GooeyTooltip";

export function WorkspacePaneControl({
  label,
  tooltip,
  icon,
  photo_url,
  show_label,
  onClick,
  event_name,
  className,
}: {
  label: string;
  /**
   * Hover text, when it says something the label does not. A labelled control names a
   * surface ("Ask Gooey"); its tooltip can name the action ("New Chat"). Defaults to
   * `label`, which is all an icon-only control needs.
   */
  tooltip?: string;
  /** FontAwesome class. Ignored when `photo_url` is set - the logo takes its place. */
  icon?: string;
  /** Renders a logo instead of an icon, for a control that identifies a surface. */
  photo_url?: string;
  /** Show `label` beside the icon/logo, turning the square button into a pill. */
  show_label?: boolean;
  onClick?: () => void;
  event_name?: string;
  className?: string;
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
