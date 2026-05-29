import "./HomePage.css";

import { HistoryWorkflowCard } from "./HistoryWorkflowCard";
import { IndustryBrowser } from "./IndustryBrowser";
import { NewsFeed } from "./NewsFeed";
import { SavedWorkflowCard } from "./SavedWorkflowCard";
import { WorkflowPicker } from "./WorkflowPicker";
import type {
  CardData,
  IndustryTile,
  NewsItem,
  WorkflowTab,
} from "./types";

type HomePageProps = {
  greeting: string | null;
  workflowTabs: WorkflowTab[];
  recentWorkflows: CardData[];
  savedWorkflows: CardData[];
  industryTiles: IndustryTile[];
  newsItems: NewsItem[];
};

export function HomePage({
  greeting,
  workflowTabs,
  recentWorkflows,
  savedWorkflows,
  industryTiles,
  newsItems,
}: HomePageProps) {
  return (
    <div className="container-xxl my-4">
      {greeting && <h1 className="mb-5">Welcome, {greeting}.</h1>}

      {recentWorkflows.length > 0 && (
        <section className="mb-5">
          <h4 className="mb-4">Recent workflows</h4>
          <div className="row row-cols-2 row-cols-md-3 row-cols-lg-4 g-3 d-flex align-items-stretch">
            {recentWorkflows.map((card) => (
              <div key={card.href} className="col">
                <HistoryWorkflowCard card={card} />
              </div>
            ))}
          </div>
        </section>
      )}

      {savedWorkflows.length > 0 && (
        <section className="mb-5">
          <div className="d-flex justify-content-between align-items-center mb-4">
            <h4>Saved workflows</h4>
            <a href="/account/saved/">
              <span className="fw-semibold small">
                View all <i className="fa-solid fa-arrow-right"></i>
              </span>
            </a>
          </div>
          <div className="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-3 d-flex align-items-stretch">
            {savedWorkflows.map((card) => (
              <div key={card.href} className="col">
                <SavedWorkflowCard card={card} />
              </div>
            ))}
          </div>
        </section>
      )}

      {workflowTabs.length > 0 && <WorkflowPicker tabs={workflowTabs} />}
      {industryTiles.length > 0 && <IndustryBrowser tiles={industryTiles} />}
      {newsItems.length > 0 && <NewsFeed items={newsItems} />}
    </div>
  );
}
