import "./HomePage/HomePage.css";

import type {
  OptionProps,
  PlaceholderProps,
  SingleValueProps,
} from "react-select";
import Select, { components } from "react-select";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "@remix-run/react";

import { HistoryWorkflowCard } from "./HomePage/workflows";
import type { CustomComponentProps } from "~/components";
import { ClientOnlySuspense } from "~/lazyImports";
import { RenderedMarkdown } from "~/renderedMarkdown";
import type {
  HistoryPageProps,
  SurfaceTabData,
  WorkflowFilterOption,
} from "@gooey-types/history_page_props";

// the tab bar and the workflow selector are set to the same height; the bar
// builds it out of padding and pill (see .surface-tabs), react-select needs
// telling directly
const FILTER_HEIGHT = 38;

export function HistoryPage({
  title,
  owner_options,
  workflow_options,
  surface_tabs,
  cards,
  load_more_href,
  empty_message,
}: CustomComponentProps & HistoryPageProps) {
  return (
    // `sidebar_page_wrapper` already supplies the container-xxl
    <div className="my-4">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-3">
        {/* mt-0 as well as mb-0: flex centres the margin box, and the app gives h1 a
            20px top margin */}
        <h1 className="my-0 d-flex align-items-baseline gap-2">
          <span>{title}</span>
          {/* on the baseline and sized to the heading's cap height, so it sits
              like a letter rather than floating above the word */}
          <i
            className="fa-regular fa-history text-muted fs-4"
            aria-hidden="true"
          />
        </h1>

        <div className="history-header-controls d-flex flex-wrap align-items-center gap-2">
          <div className="history-type-filter">
            <WorkflowFilter options={workflow_options} />
          </div>
          <OwnerFilter options={owner_options} />
        </div>
      </div>

      <div className="mb-4">
        <SurfaceSelector tabs={surface_tabs} />
      </div>

      <HistoryCardGrid
        cards={cards}
        loadMoreHref={load_more_href}
        emptyMessage={
          empty_message ?? "Nothing here yet — your runs will show up here."
        }
      />
    </div>
  );
}

export function HistoryCardGrid({
  cards,
  loadMoreHref,
  emptyMessage,
}: {
  cards: HistoryPageProps["cards"];
  loadMoreHref: string | null;
  emptyMessage: string;
}) {
  return (
    <>
      {cards.length === 0 ? (
        <p className="text-muted">{emptyMessage}</p>
      ) : (
        // one card per row on a phone: at two the 16:10 preview is too short for
        // a chat to fit without clipping
        <div className="row row-cols-1 row-cols-sm-2 row-cols-md-3 row-cols-lg-4 g-3 d-flex align-items-stretch">
          {cards.map((card, i) => (
            <div key={`${card.href}-${i}`} className="col">
              <HistoryWorkflowCard card={card} />
            </div>
          ))}
        </div>
      )}

      {loadMoreHref && (
        <div className="d-flex justify-content-center mt-5">
          <a href={loadMoreHref} className="btn btn-theme">
            Load more
          </a>
        </div>
      )}
    </>
  );
}

function OwnerFilter({ options }: { options: SurfaceTabData[] }) {
  if (options.length === 0) return null;
  return (
    <div className="btn-group min-w-0" role="group">
      {options.map((option) => (
        <Link
          key={option.id}
          to={option.href}
          className={
            "btn btn-sm d-flex align-items-center gap-2 text-nowrap " +
            (option.active ? "btn-secondary" : "btn-outline-secondary")
          }
        >
          {option.icon && (
            <span
              className="d-inline-flex align-items-center flex-shrink-0"
              aria-hidden="true"
              dangerouslySetInnerHTML={{ __html: option.icon }}
            />
          )}
          <span className="text-truncate">{option.title}</span>
        </Link>
      ))}
    </div>
  );
}

function WorkflowFilter({ options }: { options: WorkflowFilterOption[] }) {
  const navigate = useNavigate();
  if (options.length === 0) return null;

  const active = options.find((option) => option.active) ?? options[0];

  return (
    <div className="gui-input gui-input-select">
      <ClientOnlySuspense
        fallback={
          <select
            className="form-select"
            style={{ height: `${FILTER_HEIGHT}px`, border: "none" }}
            disabled
            defaultValue={active.id}
          >
            {options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.title}
              </option>
            ))}
          </select>
        }
      >
        {() => (
          <Select<WorkflowFilterOption, false>
            options={options}
            value={active}
            getOptionValue={(option) => option.id}
            getOptionLabel={(option) => option.title}
            isMulti={false}
            isClearable={false}
            styles={{
              control: (base) => ({ ...base, minHeight: FILTER_HEIGHT }),
              // above the tab strip's scroll chevrons (z-index 1), which come
              // later in the document and drew through the open menu
              menu: (base) => ({ ...base, zIndex: 5 }),
            }}
            className="mb-0 text-nowrap"
            placeholder='<i class="fa-regular fa-gift"></i> Type'
            components={{
              Option: MarkdownOption,
              SingleValue: MarkdownSingleValue,
              Placeholder: MarkdownPlaceholder,
            }}
            onChange={(option) => {
              if (!option?.href || option.id === active.id) return;
              navigate(option.href);
            }}
          />
        )}
      </ClientOnlySuspense>
    </div>
  );
}

const MarkdownOption = (props: OptionProps<WorkflowFilterOption, false>) => (
  <components.Option {...props}>
    <RenderedMarkdown
      body={props.data.title}
      className="container-margin-reset"
    />
  </components.Option>
);

const MarkdownSingleValue = ({
  children,
  ...props
}: SingleValueProps<WorkflowFilterOption, false>) => (
  <components.SingleValue {...props}>
    {children ? (
      <RenderedMarkdown
        body={children.toString()}
        className="container-margin-reset"
      />
    ) : null}
  </components.SingleValue>
);

const MarkdownPlaceholder = (
  props: PlaceholderProps<WorkflowFilterOption, false>
) => {
  if (props.children) {
    props = {
      ...props,
      children: (
        <RenderedMarkdown
          body={props.children.toString()}
          className="container-margin-reset"
        />
      ),
    };
  }
  return <components.Placeholder {...props} />;
};

function SurfaceSelector({ tabs }: { tabs: SurfaceTabData[] }) {
  const activeRef = useRef<HTMLAnchorElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const activeId = tabs.find((tab) => tab.active)?.id;
  // keep the active tab in view on initial load (deep links) and after
  // client-side navigation between surfaces (component stays mounted, so this
  // re-runs when the active surface changes).
  useEffect(() => {
    activeRef.current?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [activeId]);

  // the chevron only earns its place while there is something to its right -
  // a button that scrolls nothing is worse than no button
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const update = () => {
      setCanScrollLeft(el.scrollLeft > 1);
      setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      observer.disconnect();
    };
  }, [tabs.length]);

  if (tabs.length === 0) return null;
  return (
    // the track is the full width of the row and scrolls its tabs inside, so both
    // its ends stay round
    <div
      className={
        "surface-tabs rounded-pill bg-light flex-grow-1 min-w-0" +
        (canScrollLeft ? " surface-tabs--less" : "") +
        (canScrollRight ? " surface-tabs--more" : "")
      }
    >
      {canScrollLeft && (
        <button
          type="button"
          className="surface-tabs-scroll-btn surface-tabs-prev"
          aria-label="Show previous tabs"
          onClick={() =>
            scrollerRef.current?.scrollBy({ left: -200, behavior: "smooth" })
          }
        >
          <i className="fa-regular fa-chevron-left" aria-hidden="true" />
        </button>
      )}
      <div
        ref={scrollerRef}
        className="surface-tabs-scroll d-flex gap-1 align-items-center overflow-auto"
      >
        {tabs.map((tab) => (
          <Link
            key={tab.id}
            ref={tab.active ? activeRef : undefined}
            to={tab.href}
            className={
              "btn rounded-pill px-3 py-2 border-0 d-flex align-items-center gap-2 text-body text-decoration-none text-nowrap flex-shrink-0 workflow-tab-pill " +
              (tab.active ? "bg-white active" : "bg-transparent")
            }
          >
            {tab.icon && (
              <span dangerouslySetInnerHTML={{ __html: tab.icon }} />
            )}
            {tab.title}
          </Link>
        ))}
      </div>
      {canScrollRight && (
        <button
          type="button"
          className="surface-tabs-scroll-btn surface-tabs-next"
          aria-label="Show more tabs"
          onClick={() =>
            scrollerRef.current?.scrollBy({ left: 200, behavior: "smooth" })
          }
        >
          <i className="fa-regular fa-chevron-right" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
