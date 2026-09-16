import "./RunDebugInfo.css";
import { Link } from "@remix-run/react";
import type { ReactNode } from "react";
import type {
  AuthorProps,
  RunDebugInfoProps,
} from "@gooey-types/run_debug_info_props";
import { RunTimeline } from "./RunTimeline";

export function RunDebugInfo({
  timeline,
  source,
  conversation_title,
  conversation_url,
  run_by,
  charged_to,
  parent_run_url,
}: RunDebugInfoProps) {
  return (
    <>
      <div className="run-debug-meta">
        {source && (
          <div className="run-debug-source">
            <span className="run-debug-platform">
              <span dangerouslySetInnerHTML={{ __html: source.icon_html }} />
              {source.title}
            </span>
            {source.sender && (
              <span className="text-muted">{source.sender}</span>
            )}
          </div>
        )}
        {conversation_title && (
          <Row label="Conversation">
            {conversation_url ? (
              <Link to={conversation_url}>{conversation_title}</Link>
            ) : (
              conversation_title
            )}
          </Row>
        )}
        <Row label="Run by">
          <Author author={run_by} fallback="Unknown user" />
        </Row>
        <Row label="Charged to">
          <Author author={charged_to} fallback="No workspace" />
        </Row>
        {parent_run_url && (
          <Row label="Parent run">
            <Link to={parent_run_url}>
              View run <i className="fa-solid fa-arrow-up-right-from-square" />
            </Link>
          </Row>
        )}
      </div>
      <div className="run-debug-timeline">
        <RunTimeline {...timeline} />
      </div>
    </>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <span className="text-muted">{label}</span>
      <div className="run-debug-value">{children}</div>
    </>
  );
}

function Author({
  author,
  fallback,
}: {
  author: AuthorProps | null;
  fallback: string;
}) {
  if (!author) return <span className="text-muted">{fallback}</span>;
  const body = (
    <div className="d-flex align-items-center gap-2">
      {author.photo_url && (
        <img
          src={author.photo_url}
          alt=""
          className="run-debug-avatar rounded-circle object-fit-cover"
        />
      )}
      {author.name}
    </div>
  );
  return author.url ? <Link to={author.url}>{body}</Link> : body;
}
