import "./RecipeWorkspace/RecipeWorkspace.css";

import clsx from "clsx";
import { GooeyTooltip } from "./GooeyTooltip";

export function WorkspacePaneControl({
  label,
  icon,
  onClick,
  event_name,
  className,
}: {
  label: string;
  icon: string;
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

  return (
    <GooeyTooltip content={label} placement="bottom" fitContent>
      <button
        type="button"
        className={clsx("v2-pane-control", className)}
        onClick={handleClick}
        aria-label={label}
      >
        <i className={icon} />
      </button>
    </GooeyTooltip>
  );
}
