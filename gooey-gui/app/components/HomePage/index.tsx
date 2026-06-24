import "./HomePage.css";

import { IndustryBrowser } from "./IndustryBrowser";
import { NewsFeed } from "./NewsFeed";
import {
  HistoryWorkflowCard,
  SavedWorkflowCard,
  WorkflowPicker,
} from "./workflows";
import { WorkspaceHeader } from "./WorkspaceHeader";
import type { CustomComponentProps } from "~/components";
import type { HomePageProps } from "@gooey-types/home_page_props";

export function HomePage({
  greeting,
  workspace_header,
  recent_workflows,
  saved_workflows,
  saved_workflows_href,
  workflow_tabs,
  industry_tiles,
  news_items,
}: CustomComponentProps & HomePageProps) {
  return (
    <div className="mt-4">
      {workspace_header && <WorkspaceHeader header={workspace_header} />}
      {greeting && <h1 className="mb-5">Welcome, {greeting}.</h1>}

      {recent_workflows.length > 0 && (
        <section className="mb-5">
          <h4 className="mb-4">Recent workflows</h4>
          <div className="row row-cols-1 row-cols-md-3 row-cols-lg-4 g-3 d-flex align-items-stretch">
            {recent_workflows.map((card) => (
              <div key={card.href} className="col">
                <HistoryWorkflowCard card={card} />
              </div>
            ))}
          </div>
        </section>
      )}

      {saved_workflows.length > 0 && (
        <section className="mb-5">
          <div className="d-flex justify-content-between align-items-center mb-4">
            <h4>Saved workflows</h4>
            <a href={saved_workflows_href}>
              <span className="fw-semibold small">
                View all <i className="fa-solid fa-arrow-right"></i>
              </span>
            </a>
          </div>
          <div className="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-3 align-items-start">
            {saved_workflows.map((card) => (
              <div key={card.href} className="col">
                <SavedWorkflowCard card={card} />
              </div>
            ))}
          </div>
        </section>
      )}

      {workflow_tabs.length > 0 && <WorkflowPicker tabs={workflow_tabs} />}
      {industry_tiles.length > 0 && <IndustryBrowser tiles={industry_tiles} />}
      {news_items.length > 0 && <NewsFeed items={news_items} />}
    </div>
  );
}
