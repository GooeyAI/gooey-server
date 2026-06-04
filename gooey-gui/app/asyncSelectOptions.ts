import { useEffect, useRef, useState } from "react";
import { useDebouncedCallback } from "use-debounce";

export type AsyncOption = { value: string; label: string };

export type AsyncOptionsResponse = {
  options: AsyncOption[];
  nextOptionsPage: number | null;
};

const ASYNC_OPTIONS_CACHE_MAX = 64;
const asyncOptionsCache = new Map<string, Promise<AsyncOptionsResponse>>();

export function useAsyncSelectOptions({
  asyncOptionsUrl,
  initialOptions,
  initialNextOptionsPage,
  keepOnSearch,
  debounceMs = 300,
}: {
  asyncOptionsUrl?: string;
  initialOptions: AsyncOption[];
  initialNextOptionsPage: number | null;
  keepOnSearch: (option: AsyncOption) => boolean;
  debounceMs?: number;
}) {
  let isAsync = Boolean(asyncOptionsUrl);
  let [options, setOptions] = useState<AsyncOption[]>(initialOptions);
  let [nextOptionsPage, setNextOptionsPage] = useState(initialNextOptionsPage);
  let [loading, setLoading] = useState(false);
  let [query, setQuery] = useState("");

  let latestRequestRef = useRef(0);
  let nextOptionsPageRef = useRef(nextOptionsPage);
  let queryRef = useRef(query);
  let keepOnSearchRef = useRef(keepOnSearch);
  nextOptionsPageRef.current = nextOptionsPage;
  queryRef.current = query;
  keepOnSearchRef.current = keepOnSearch;

  // The server re-parses the render tree on every update, so `initialOptions`
  // is a fresh array instance even when its contents are unchanged. Key the
  // reset on a stable content signature so lazily-loaded pages and the active
  // search query survive unrelated re-renders, and only reset when the SSR
  // options/url actually change.
  let resetKey =
    `${asyncOptionsUrl ?? ""}|${initialNextOptionsPage ?? ""}|` +
    initialOptions.map((option) => option.value).join(",");
  useEffect(() => {
    setOptions(initialOptions);
    setNextOptionsPage(initialNextOptionsPage);
    setQuery("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey]);

  let loadPage = async ({
    page,
    searchQuery,
    replace,
  }: {
    page: number | null;
    searchQuery: string;
    replace: boolean;
  }) => {
    if (!asyncOptionsUrl || page === null) return;
    let requestId = ++latestRequestRef.current;
    setLoading(true);
    try {
      let data = await fetchOptionsPage(asyncOptionsUrl, page, searchQuery);
      if (requestId !== latestRequestRef.current) return;
      setOptions((currentOptions) => {
        let baseOptions = replace
          ? currentOptions.filter((option) => keepOnSearchRef.current(option))
          : currentOptions;
        return mergeOptions(baseOptions, data.options);
      });
      setNextOptionsPage(data.nextOptionsPage);
    } catch (err) {
      console.error("Failed to load select options", err);
    } finally {
      if (requestId === latestRequestRef.current) setLoading(false);
    }
  };

  let loadMore = () =>
    loadPage({
      page: nextOptionsPageRef.current,
      searchQuery: queryRef.current,
      replace: false,
    });

  let debouncedSearch = useDebouncedCallback((searchQuery: string) => {
    loadPage({ page: 0, searchQuery, replace: true });
  }, debounceMs);

  let search = (searchQuery: string) => {
    setQuery(searchQuery);
    debouncedSearch(searchQuery);
  };

  return { isAsync, options, loading, loadMore, search };
}

async function fetchOptionsPage(
  asyncOptionsUrl: string,
  page: number,
  query: string
): Promise<AsyncOptionsResponse> {
  let url = new URL(asyncOptionsUrl, window.location.origin);
  url.searchParams.set("page", String(page));
  if (query) {
    url.searchParams.set("q", query);
  } else {
    url.searchParams.delete("q");
  }
  let cacheKey = url.toString();
  let cached = asyncOptionsCache.get(cacheKey);
  if (cached) return cached;

  let responsePromise = (async (): Promise<AsyncOptionsResponse> => {
    let response = await fetch(cacheKey);
    if (!response.ok) {
      throw new Error(`Failed to load options (status ${response.status})`);
    }
    let data = await response.json();
    return {
      options: data.options ?? [],
      nextOptionsPage: data.nextOptionsPage ?? null,
    };
  })();

  responsePromise.catch(() => asyncOptionsCache.delete(cacheKey));
  if (asyncOptionsCache.size >= ASYNC_OPTIONS_CACHE_MAX) {
    let oldestKey = asyncOptionsCache.keys().next().value;
    if (oldestKey) {
      asyncOptionsCache.delete(oldestKey);
    }
  }
  asyncOptionsCache.set(cacheKey, responsePromise);
  return responsePromise;
}

function mergeOptions(currentOptions: AsyncOption[], newOptions: AsyncOption[]) {
  let currentValues = new Set(currentOptions.map((option) => option.value));
  let dedupedOptions = newOptions.filter(
    (option) => !currentValues.has(option.value)
  );
  return [...currentOptions, ...dedupedOptions];
}

export function optionSelected(
  option: AsyncOption,
  value: string | string[] | null | undefined,
  isMulti: boolean
) {
  if (isMulti) {
    return Array.isArray(value) && value.includes(option.value);
  }
  return option.value === value;
}
