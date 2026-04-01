import { useEffect, useState } from "react";

export function useEventSourceNullOk(
  url: string | URL | null | undefined,
  {
    event = "message",
    init,
  }: {
    event?: string;
    init?: EventSourceInit;
  } = {}
) {
  const [data, setData] = useState<string | null>(null);

  useEffect(() => {
    if (!url) return;

    const eventSource = new EventSource(url, init);
    eventSource.addEventListener(event ?? "message", handler);
    // eventSource.addEventListener("open", () => {
    //   console.log("> connected to:", url);
    // });

    // rest data if dependencies change
    setData(null);

    function handler(event: MessageEvent) {
      setData(event.data || "UNKNOWN_EVENT_DATA");
    }

    return () => {
      eventSource.removeEventListener(event ?? "message", handler);
      eventSource.close();
      // console.log("> disconnected from:", url);
    };
  }, [url, event, init]);

  return data;
}
