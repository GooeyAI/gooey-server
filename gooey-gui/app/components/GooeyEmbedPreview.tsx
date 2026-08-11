import { useEffect, useRef } from "react";
import type { CustomComponentProps } from "~/components";
import { fetchServerAPI } from "~/fetchServerAPI";

declare global {
  interface Window {
    GooeyEmbed?: any;
  }
}

type MountedEntry = { innerDiv: HTMLElement; root: { unmount(): void } };

/**
 * Mounts once per `embed_key` (the published run) and on nothing else - a Run must leave the
 * mounted widget alone or it would restart the conversation for nothing.
 *
 * Theme and branding go through `updateConfig`, which reskins in place: the widget reads both
 * from its own reactive config state, so neither needs a remount to land.
 */
export function GooeyEmbedPreview(
  props: CustomComponentProps & {
    embed_key: string;
    config: Record<string, any>;
    messages?: Array<Record<string, any>> | null;
    run_url: string;
    className?: string;
    style?: Record<string, string | number>;
  }
) {
  const { embed_key, config, messages, className, style } = props;
  const propsRef = useRef(props);
  propsRef.current = props;

  const controllerRef = useRef<any>(null);
  const mountedRef = useRef<MountedEntry | null>(null);

  useEffect(() => {
    const loadEmbed = () => {
      const GooeyEmbed = window.GooeyEmbed;
      if (!GooeyEmbed || mountedRef.current) return;

      const embedTarget = document.getElementById("gooey-embed");
      if (!embedTarget) return;

      controllerRef.current = {
        messages: propsRef.current.messages,
        onSendMessage: (payload: unknown) => {
          const btn = document.getElementById(
            "onSendMessage"
          ) as HTMLInputElement | null;
          if (!btn) return;
          btn.value = JSON.stringify(payload);
          btn.click();
        },
        onNewConversation: () => {
          document.getElementById("onNewConversation")?.click();
        },
        fetchConversations: () =>
          fetchServerAPI("/__/agent/fetch-conversations", {
            run_url: propsRef.current.run_url,
          }),
      };

      GooeyEmbed.mount(propsRef.current.config, controllerRef.current);

      // mount() appends its {innerDiv, root} to _mounted; that entry is what this component owns
      const mounted = GooeyEmbed._mounted;
      mountedRef.current = Array.isArray(mounted)
        ? (mounted[mounted.length - 1] ?? null)
        : null;
    };

    // the lib is a plain <script> tag, so it may not have run yet on a cold load
    const script = document.getElementById("gooey-embed-script");
    script?.addEventListener("load", loadEmbed);
    loadEmbed();

    return () => {
      script?.removeEventListener("load", loadEmbed);

      const entry = mountedRef.current;
      mountedRef.current = null;
      controllerRef.current = null;
      if (!entry) return;

      try {
        entry.root.unmount();
      } catch {
        // already torn down - detaching the node is all that is left to do
      }
      entry.innerDiv.remove();

      const mounted = window.GooeyEmbed?._mounted;
      if (Array.isArray(mounted)) {
        const idx = mounted.indexOf(entry);
        if (idx >= 0) mounted.splice(idx, 1);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [embed_key]);

  useEffect(() => {
    controllerRef.current?.setMessages?.(messages);
  }, [messages]);

  useEffect(() => {
    controllerRef.current?.updateConfig?.({
      theme: config.theme,
      branding: config.branding,
    });
  }, [config.theme, config.branding]);

  return <div id="gooey-embed" className={className} style={style} />;
}
