import * as Sentry from "@sentry/remix";
import { useLocation, useNavigate } from "@remix-run/react";
import { useEffect, useRef, useState } from "react";
import { useDebouncedCallback } from "use-debounce";
import AsyncSelect from "react-select/async";
import type {
  MemoryEntryDetail,
  MemoryEntryRow,
  MemoryFilterField,
  MemoryFilterOption,
  WorkspaceMemoryTableProps,
} from "@gooey-types/workspace_memory_props";
import type { CustomComponentProps } from "~/components";
import { fetchServerAPI } from "~/fetchServerAPI";
import { ClientOnlySuspense } from "~/lazyImports";

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

type MemoryFiltersProps = {
  filters: MemoryFilterField[];
  search: string;
  optionsUrl: string;
};

type MemorySearchBoxProps = {
  search: string;
  onSubmit: (value: string) => void;
};

type MemoryFilterSelectProps = {
  filter: MemoryFilterField;
  optionsUrl: string;
  onChange: (option: MemoryFilterOption | null) => void;
};

type DeleteButtonProps = {
  entry: MemoryEntryRow;
  onClick: () => void;
};

export function WorkspaceMemoryTable({
  description,
  filters,
  options_url,
  search,
  entries: initialEntries,
  next_page_url,
  delete_url,
}: CustomComponentProps & WorkspaceMemoryTableProps) {
  const [entries, setEntries] = useState(initialEntries);
  // Re-sync when the server sends a new list (e.g. after filtering or paging),
  // since this component instance is reused across client-side navigations.
  useEffect(() => {
    setEntries(initialEntries);
  }, [initialEntries]);
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

      <MemoryFilters
        filters={filters}
        search={search}
        optionsUrl={options_url}
      />

      {entries.length === 0 ? (
        <p className="text-muted small">
          {filters.some((filter) => filter.selected) || search
            ? "No memory entries match the current search or filters."
            : `No memory entries yet. They appear here when a Function or Copilot tool writes to Gooey Memory.`}
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

function MemoryFilters({ filters, search, optionsUrl }: MemoryFiltersProps) {
  const navigate = useNavigate();
  const location = useLocation();

  // Build the query string from the current filters + search, overriding a
  // single filter or the search term so changing one control preserves the rest.
  const navigateWith = ({
    filterKey,
    filterOption,
    searchValue,
  }: {
    filterKey?: string;
    filterOption?: MemoryFilterOption | null;
    searchValue?: string;
  }) => {
    const params = new URLSearchParams();
    for (const filter of filters) {
      const selected =
        filterKey !== undefined && filter.key === filterKey
          ? filterOption
          : filter.selected;
      if (selected) params.set(filter.key, selected.value);
    }
    const nextSearch = searchValue !== undefined ? searchValue : search;
    if (nextSearch) params.set("search", nextSearch);
    const query = params.toString();
    navigate(query ? `${location.pathname}?${query}` : location.pathname);
  };

  return (
    <div className="mb-4">
      <MemorySearchBox
        search={search}
        onSubmit={(value) => navigateWith({ searchValue: value })}
      />
      <div className="d-flex flex-wrap gap-2">
        {filters.map((filter) => (
          <MemoryFilterSelect
            key={filter.key}
            filter={filter}
            optionsUrl={optionsUrl}
            onChange={(option) =>
              navigateWith({ filterKey: filter.key, filterOption: option })
            }
          />
        ))}
      </div>
    </div>
  );
}

// Survives the remount that a search-triggered navigation causes, so we can
// restore focus to the search box afterwards (otherwise it blurs after every
// keystroke-driven search, breaking the search-as-you-type flow).
let pendingSearchFocus = false;

function MemorySearchBox({ search, onSubmit }: MemorySearchBoxProps) {
  const [value, setValue] = useState(search);
  const inputRef = useRef<HTMLInputElement>(null);
  // Track the value we last pushed to the URL, so the re-render that navigation
  // triggers doesn't clobber characters typed while the request was in flight.
  const lastSubmittedRef = useRef(search);

  // Re-sync only on *external* changes (back/forward, filter nav), not on the
  // echo of our own search navigation.
  useEffect(() => {
    if (search !== lastSubmittedRef.current) {
      lastSubmittedRef.current = search;
      setValue(search);
    }
  }, [search]);

  // After a search navigation re-renders this component, put the cursor back so
  // the user can keep typing without clicking into the box again.
  useEffect(() => {
    if (!pendingSearchFocus || !inputRef.current) return;
    pendingSearchFocus = false;
    const el = inputRef.current;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, [search]);

  const runSearch = (next: string) => {
    lastSubmittedRef.current = next;
    pendingSearchFocus = true;
    onSubmit(next);
  };

  const debouncedSearch = useDebouncedCallback(runSearch, 400);

  return (
    <div className="position-relative mb-3" style={{ maxWidth: "600px" }}>
      <i
        className="fa-solid fa-magnifying-glass position-absolute text-muted"
        style={{
          top: "50%",
          left: "1rem",
          transform: "translateY(-50%)",
          pointerEvents: "none",
          fontSize: "0.9em",
        }}
        aria-hidden="true"
      />
      <input
        ref={inputRef}
        type="text"
        // The whole gooey page is one <form> that auto-submits on input changes;
        // opt out so typing here doesn't trigger a server round-trip that wipes
        // the field. We navigate explicitly (debounced) instead.
        // No `form-control` class: it forces a white bg via `!important`, which
        // would override the `bg-light` pill used by the /explore search bar.
        data-submit-disabled
        className="bg-light border-0 rounded-pill"
        style={{ width: "100%", padding: "0.8rem 2.7rem", fontSize: "1rem" }}
        placeholder="Search keys..."
        aria-label="Search memory keys"
        autoComplete="off"
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          debouncedSearch(e.target.value.trim());
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            // Stop the surrounding gooey form from submitting, and search now.
            e.preventDefault();
            debouncedSearch.cancel();
            runSearch(value.trim());
          }
        }}
      />
      {value ? (
        <button
          type="button"
          data-submit-disabled
          className="btn btn-link text-muted p-0 position-absolute"
          style={{ top: "50%", right: "1rem", transform: "translateY(-50%)" }}
          aria-label="Clear search"
          onClick={() => {
            debouncedSearch.cancel();
            setValue("");
            runSearch("");
          }}
        >
          <i className="fa-regular fa-xmark-large" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}

function MemoryFilterSelect({
  filter,
  optionsUrl,
  onChange,
}: MemoryFilterSelectProps) {
  const [defaultOptions, setDefaultOptions] = useState<MemoryFilterOption[]>(
    []
  );
  const [isLoading, setIsLoading] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  // AsyncSelect calls loadOptions on every keystroke; resolve superseded
  // promises so only the latest debounced fetch updates the menu.
  const pendingResolveRef = useRef<
    ((options: MemoryFilterOption[]) => void) | null
  >(null);

  const fetchOptions = async (search: string) => {
    const data = await fetchServerAPI<{ options: MemoryFilterOption[] }>(
      optionsUrl,
      { field: filter.key, search }
    );
    return data.options;
  };

  const runDebouncedSearch = useDebouncedCallback(async (search: string) => {
    setIsLoading(true);
    try {
      const options = await fetchOptions(search);
      pendingResolveRef.current?.(options);
    } catch (err) {
      console.error(err);
      Sentry.captureException(err);
      pendingResolveRef.current?.([]);
    } finally {
      pendingResolveRef.current = null;
      setIsLoading(false);
    }
  }, 400);

  const loadOptions = (search: string) => {
    if (pendingResolveRef.current) {
      pendingResolveRef.current([]);
    }
    return new Promise<MemoryFilterOption[]>((resolve) => {
      pendingResolveRef.current = resolve;
      runDebouncedSearch(search);
    });
  };

  // Defer the first request until the user actually opens the dropdown.
  const handleMenuOpen = async () => {
    if (hasLoaded) return;
    setHasLoaded(true);
    setIsLoading(true);
    try {
      setDefaultOptions(await fetchOptions(""));
    } catch (err) {
      console.error(err);
      Sentry.captureException(err);
      setDefaultOptions([]);
    } finally {
      setIsLoading(false);
    }
  };

  const placeholder = (
    <span className="d-inline-flex align-items-center gap-2 text-muted">
      <span
        className="d-inline-flex align-items-center"
        dangerouslySetInnerHTML={{ __html: filter.icon ?? "" }}
      />
      {filter.label}
    </span>
  );

  return (
    <div style={{ flex: "0 0 220px", maxWidth: "220px" }}>
      <ClientOnlySuspense
        fallback={
          <div className="form-control d-flex align-items-center text-muted text-truncate">
            {filter.selected ? filter.selected.label : placeholder}
          </div>
        }
      >
        {() => (
          <AsyncSelect<MemoryFilterOption, false>
            isClearable
            cacheOptions
            defaultOptions={defaultOptions}
            isLoading={isLoading}
            onMenuOpen={handleMenuOpen}
            value={filter.selected}
            loadOptions={loadOptions}
            onChange={(option) => onChange(option ?? null)}
            getOptionValue={(option) => option.value}
            getOptionLabel={(option) => option.label}
            formatOptionLabel={(option) => (
              <MemoryFilterOptionLabel option={option} />
            )}
            placeholder={placeholder}
            menuPortalTarget={
              typeof document !== "undefined" ? document.body : undefined
            }
            styles={{
              menuPortal: (base) => ({ ...base, zIndex: 9999 }),
            }}
          />
        )}
      </ClientOnlySuspense>
    </div>
  );
}

function MemoryFilterOptionLabel({ option }: { option: MemoryFilterOption }) {
  return (
    <span className="d-inline-flex align-items-center gap-2">
      {option.icon ? (
        <span
          className="d-inline-flex align-items-center"
          dangerouslySetInnerHTML={{ __html: option.icon }}
        />
      ) : null}
      <span className="text-truncate">{option.label}</span>
    </span>
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
          key={detail.icon}
          className="d-inline-flex align-items-center gap-2 text-break"
        >
          <i
            className="fa-fw"
            dangerouslySetInnerHTML={{ __html: detail.icon }}
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
