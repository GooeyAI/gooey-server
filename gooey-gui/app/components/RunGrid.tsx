import "./HomePage/HomePage.css";

import type { CustomComponentProps } from "~/components";
import type { RunGridProps } from "@gooey-types/run_grid_props";

import { HistoryCardGrid } from "./HistoryPage";

export function RunGrid({
  cards,
  load_more_href,
  empty_message,
}: CustomComponentProps & RunGridProps) {
  return (
    <div className="container-xxl py-4">
      <HistoryCardGrid
        cards={cards}
        loadMoreHref={load_more_href}
        emptyMessage={empty_message}
      />
    </div>
  );
}
