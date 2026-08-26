import "./HomePage/HomePage.css";

import type { CustomComponentProps } from "~/components";
import type { UsagePageProps } from "@gooey-types/usage_page_props";

import { HistoryCardGrid } from "./HistoryPage";

export function UsagePage({
  cards,
  load_more_href,
  empty_message,
}: CustomComponentProps & UsagePageProps) {
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
