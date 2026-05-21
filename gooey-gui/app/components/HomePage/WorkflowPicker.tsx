import { useState } from "react";

import { SavedWorkflowCard } from "./SavedWorkflowCard";
import type { WorkflowTab } from "./types";

export function WorkflowPicker({ tabs }: { tabs: WorkflowTab[] }) {
  const [activeIdx, setActiveIdx] = useState(0);
  const activeTab = tabs[activeIdx];

  return (
    <section className="mb-5">
      <h4 className="mb-4">What will you build today?</h4>

      <div className="d-inline-flex p-1 rounded-pill mb-4 gap-1 align-items-center bg-light">
        {tabs.map((tab, i) => (
          <button
            key={tab.id}
            type="button"
            className={
              "btn rounded-pill px-3 py-2 border-0 d-flex align-items-center gap-2 text-body workflow-tab-pill " +
              (i === activeIdx ? "bg-white active" : "bg-transparent")
            }
            onClick={() => setActiveIdx(i)}
          >
            {tab.icon && (
              <span dangerouslySetInnerHTML={{ __html: tab.icon }} />
            )}
            {tab.title}
          </button>
        ))}
      </div>

      {activeTab.cards.length === 0 ? (
        <p className="text-muted small">No workflows yet — check back soon.</p>
      ) : (
        <div className="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-3 d-flex align-items-stretch">
          {activeTab.cards.map((card) => (
            <div key={card.href} className="col">
              <SavedWorkflowCard card={card} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
