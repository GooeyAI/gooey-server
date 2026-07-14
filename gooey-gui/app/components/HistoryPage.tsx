import "./HomePage/HomePage.css";

import type {
  OptionProps,
  PlaceholderProps,
  SingleValueProps,
} from "react-select";
import Select, { components } from "react-select";
import { useEffect, useRef } from "react";
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

export function HistoryPage({
  title,
  workflow_options,
  surface_tabs,
  cards,
  load_more_href,
  empty_message,
}: CustomComponentProps & HistoryPageProps) {
  return (
    <div className="container-xxl my-4">
      <h1 className="mb-4">{title}</h1>

      <div className="d-flex flex-column flex-lg-row align-items-lg-center justify-content-lg-between gap-3 mb-4">
        <SurfaceSelector tabs={surface_tabs} />
        <div className="flex-grow-1 mt-2" style={{ width: "300px" }}>
          <WorkflowFilter options={workflow_options} />
        </div>
      </div>

      {cards.length === 0 ? (
        <p className="text-muted">
          {empty_message ?? "Nothing here yet — your runs will show up here."}
        </p>
      ) : (
        <div className="row row-cols-2 row-cols-md-3 row-cols-lg-4 g-3 d-flex align-items-stretch">
          {cards.map((card, i) => (
            <div key={`${card.href}-${i}`} className="col">
              <HistoryWorkflowCard card={card} />
            </div>
          ))}
        </div>
      )}

      {load_more_href && (
        <div className="d-flex justify-content-center mt-5">
          <a href={load_more_href} className="btn btn-theme">
            Load more
          </a>
        </div>
      )}
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
            style={{ height: "38px", border: "none" }}
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
  const activeId = tabs.find((tab) => tab.active)?.id;
  // keep the active tab in view on initial load (deep links) and after
  // client-side navigation between surfaces (component stays mounted, so this
  // re-runs when the active surface changes).
  useEffect(() => {
    activeRef.current?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [activeId]);

  if (tabs.length === 0) return null;
  return (
    <div className="overflow-auto workflow-tab-scroll flex-grow-1 min-w-0">
      <div className="d-inline-flex p-1 rounded-pill gap-1 align-items-center bg-light">
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
    </div>
  );
}
