import type { RunTimelineProps } from "@gooey-types/run_timeline_props";
import type { CustomComponentProps } from "~/components";

export function RunTimeline({
  created_at,
  started_at,
  finished_at,
}: CustomComponentProps & RunTimelineProps) {
  const createdAt = new Date(created_at);
  const startedAt = new Date(started_at);
  const finishedAt = new Date(finished_at);
  return (
    <div className="d-flex align-items-start my-3">
      <Milestone
        icon="fa-sharp-duotone fa-solid fa-spinner"
        label="Created"
        date={createdAt}
      />
      <Connector
        icon="fa-solid fa-hourglass-half"
        label="Queued"
        from={createdAt}
        to={startedAt}
      />
      <Milestone icon="fa-solid fa-play" label="Started" date={startedAt} />
      <Connector
        icon="fa-solid fa-stopwatch"
        label="Run Time"
        from={startedAt}
        to={finishedAt}
      />
      <Milestone
        icon="fa-solid fa-flag-checkered"
        label="Finished"
        date={finishedAt}
      />
    </div>
  );
}

// height of the icon row, so connector lines pass through its center
const ICON_ROW_HEIGHT = 20;

function Milestone({
  icon,
  label,
  date,
}: {
  icon: string;
  label: string;
  date: Date;
}) {
  return (
    <div className="d-flex flex-column align-items-center text-center">
      <div
        className="d-flex align-items-center"
        style={{ height: ICON_ROW_HEIGHT }}
      >
        <i className={icon} />
      </div>
      <div className="mt-1 fw-bold">{label}</div>
      <div className="text-muted small">{formatLocalDateTime(date)}</div>
    </div>
  );
}

function Connector({
  icon,
  label,
  from,
  to,
}: {
  icon: string;
  label: string;
  from: Date;
  to: Date;
}) {
  const seconds = (to.getTime() - from.getTime()) / 1000;
  return (
    <div
      className="flex-grow-1 d-flex flex-column align-items-center px-2"
      style={{ minWidth: 80 }}
    >
      {/* offset the line so it passes through the center of the dots */}
      <div
        className="w-100 border-top border-dark"
        style={{ marginTop: ICON_ROW_HEIGHT / 2 }}
      />
      <div className="mt-1 text-muted small">
        <i className={`${icon} me-1`} />
        {label}: {seconds.toFixed(2)}s
      </div>
    </div>
  );
}

function formatLocalDateTime(date: Date): string {
  const dateOptions: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
  };
  if (date.getFullYear() !== new Date().getFullYear()) {
    dateOptions.year = "numeric";
  }
  const datePart = date.toLocaleDateString("en-IN", dateOptions);
  const timePart = date
    .toLocaleTimeString("en-IN", {
      hour: "numeric",
      minute: "numeric",
      second: "numeric",
      hour12: true,
    })
    .toUpperCase();
  return `${datePart}, ${timePart}`;
}
