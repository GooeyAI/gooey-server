import "./RecipeWorkspace/RecipeWorkspace.css";

import clsx from "clsx";

import type {
  EventControlTarget,
  FontAwesomeIcon,
  PanelControlTarget,
  PhotoIcon,
  WorkspacePaneControlProps,
} from "@gooey-types/recipe_workspace_props";
import { useAppShellPanelActions } from "~/appShellContext";

import { GooeyTooltip } from "./GooeyTooltip";

type ControlIcon = FontAwesomeIcon | PhotoIcon;
type ControlTarget = PanelControlTarget | EventControlTarget;

type SharedProps = {
  label: string;
  icon: ControlIcon;
  tooltip?: string | null;
  show_label?: boolean;
  className?: string | null;
};

export function WorkspacePaneControl(props: WorkspacePaneControlProps) {
  const { setPanelOpen } = useAppShellPanelActions();
  const handleClick = () => runTarget(props.target, setPanelOpen);
  return <PaneControlButton {...props} onClick={handleClick} />;
}

export function LocalWorkspacePaneControl({
  onClick,
  ...props
}: SharedProps & { onClick: () => void }) {
  return <PaneControlButton {...props} onClick={onClick} />;
}

function PaneControlButton({
  label,
  tooltip = null,
  icon,
  show_label = false,
  onClick,
  className,
}: SharedProps & { onClick: () => void }) {
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
      onClick={onClick}
      aria-label={accessibleName}
    >
      {icon.kind === "photo" ? (
        <img className="v2-pane-control-photo" src={icon.url} alt="" />
      ) : (
        <i className={icon.class_name} />
      )}
      {show_label && <span className="v2-pane-control-label">{label}</span>}
    </button>
  );

  if (show_label && !tooltip) {
    return button;
  }
  return (
    <GooeyTooltip content={tooltip || label} placement="bottom" fitContent>
      {button}
    </GooeyTooltip>
  );
}

function runTarget(
  target: ControlTarget,
  setPanelOpen: (key: string, open: boolean) => void
) {
  if (target.kind === "panel") {
    setPanelOpen(target.panel_key, target.open);
    return;
  }
  window.dispatchEvent(new Event(target.event_name));
}
