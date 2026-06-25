import * as Sentry from "@sentry/remix";
import { useState } from "react";
import type {
  MemoryEntryDetail,
  MemoryEntryRow,
  WorkspaceMemoryTableProps,
} from "@gooey-types/workspace_memory_props";
import type { CustomComponentProps } from "~/components";
import { fetchServerAPI } from "~/fetchServerAPI";

type MemoryEntryCardProps = {
  entry: MemoryEntryRow;
  onRequestDelete: () => void;
};

type MemoryValueProps = {
  entry: MemoryEntryRow;
};

type MemoryEntryDetailsProps = {
  details: MemoryEntryDetail[];
};

type DeleteButtonProps = {
  entry: MemoryEntryRow;
  onClick: () => void;
};

export function WorkspaceMemoryTable({
  description,
  entries: initialEntries,
  next_page_url,
  delete_url,
}: CustomComponentProps & WorkspaceMemoryTableProps) {
  const [entries, setEntries] = useState(initialEntries);
  const [pendingDelete, setPendingDelete] = useState<MemoryEntryRow | null>(
    null
  );
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const confirmDelete = async () => {
    if (!pendingDelete || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await fetchServerAPI<{ success: boolean }>(delete_url, {
        user_id: pendingDelete.user_id,
        key: pendingDelete.key,
      });
      setEntries((prev) =>
        prev.filter(
          (entry) =>
            entry.user_id !== pendingDelete.user_id ||
            entry.key !== pendingDelete.key
        )
      );
      setPendingDelete(null);
    } catch (err) {
      console.error(err);
      Sentry.captureException(err);
      setDeleteError(
        err instanceof Error ? err.message : "Failed to delete memory entry."
      );
    }
    setIsDeleting(false);
  };

  const requestDelete = (entry: MemoryEntryRow) => {
    setDeleteError(null);
    setPendingDelete(entry);
  };

  return (
    <div>
      <h2 className="mb-3">
        <i className="fa-regular fa-brain me-2" aria-hidden="true" />
        Gooey Memory
      </h2>

      <p className="text-muted">{description}</p>

      {entries.length === 0 ? (
        <p className="text-muted small">
          No memory entries yet. They appear here when a Function or Copilot
          tool writes to Gooey Memory.
        </p>
      ) : (
        <div>
          {entries.map((entry) => (
            <MemoryEntryCard
              key={JSON.stringify([entry.user_id, entry.key])}
              entry={entry}
              onRequestDelete={() => requestDelete(entry)}
            />
          ))}
        </div>
      )}

      {next_page_url ? (
        <div className="text-center my-4">
          <a href={next_page_url} className="btn btn-theme btn-secondary">
            Load more
          </a>
        </div>
      ) : null}

      {pendingDelete ? (
        <div
          className="modal show d-block"
          tabIndex={-1}
          role="dialog"
          style={{ backgroundColor: "rgba(0, 0, 0, 0.45)" }}
        >
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Delete Memory Entry</h5>
                <button
                  type="button"
                  className="btn-close"
                  aria-label="Close"
                  disabled={isDeleting}
                  onClick={() => setPendingDelete(null)}
                />
              </div>
              <div className="modal-body">
                <p>
                  Are you sure you want to delete{" "}
                  <code>{pendingDelete.key}</code>?
                </p>
                <p className="text-muted small mb-0">
                  Functions and tools that depend on this value may fail or
                  behave unexpectedly.
                </p>
                {deleteError ? (
                  <div
                    className="alert alert-danger py-2 mt-3 mb-0"
                    role="alert"
                  >
                    {deleteError}
                  </div>
                ) : null}
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-tertiary"
                  disabled={isDeleting}
                  onClick={() => setPendingDelete(null)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={isDeleting}
                  onClick={confirmDelete}
                >
                  {isDeleting ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MemoryEntryCard({ entry, onRequestDelete }: MemoryEntryCardProps) {
  return (
    <div className="border rounded-3 p-3 mb-3">
      <div className="d-flex justify-content-between align-items-start gap-2 mb-2">
        <code className="text-break fw-bold">{entry.key}</code>
        <DeleteButton entry={entry} onClick={onRequestDelete} />
      </div>
      <div className="mb-3">
        <MemoryValue entry={entry} />
      </div>
      <MemoryEntryDetails details={entry.details} />
      <div className="d-flex justify-content-between align-items-center gap-2 small text-muted">
        <span
          className="d-inline-flex align-items-center gap-2 text-break"
          dangerouslySetInnerHTML={{ __html: entry.scope.label }}
        />
        <span className="text-nowrap">{entry.updated_at_label}</span>
      </div>
    </div>
  );
}

function MemoryValue({ entry }: MemoryValueProps) {
  const code = formatValueCode(entry.value);

  return (
    <pre
      className="mb-0 p-3 rounded overflow-auto container-margin-reset"
      style={{
        backgroundColor: "#1e1e1e",
        color: "#d4d4d4",
        fontSize: "0.85rem",
        maxHeight: "300px",
      }}
    >
      <code className="text-reset">{code}</code>
    </pre>
  );
}

function MemoryEntryDetails({ details }: MemoryEntryDetailsProps) {
  if (details.length === 0) return null;

  return (
    <div className="d-flex flex-wrap align-items-center gap-3 small text-muted mb-3">
      {details.map((detail) => (
        <span
          key={detail.label}
          className="d-inline-flex align-items-center gap-2 text-break"
        >
          <i
            className={`${detail.icon} fa-fw`}
            title={detail.label}
            aria-label={detail.label}
          />
          <span className="text-break">{detail.value}</span>
        </span>
      ))}
    </div>
  );
}

function DeleteButton({ entry, onClick }: DeleteButtonProps) {
  return (
    <button
      type="button"
      className="btn btn-tertiary text-danger p-0 m-0 flex-shrink-0"
      aria-label={`Delete ${entry.key}`}
      onClick={onClick}
    >
      <i className="fa-solid fa-trash-can" aria-hidden="true" />
    </button>
  );
}

function formatValueCode(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value, null, 2);
}
