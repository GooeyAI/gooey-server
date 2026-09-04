import { useEffect, useRef } from "react";
import type { CustomComponentProps } from "~/components";
import { fetchServerAPI } from "~/fetchServerAPI";

declare global {
  interface Window {
    GooeyEmbed?: any;
  }
}

/**
 * Mounts the copilot chat preview once, and never remounts it.
 *
 * Everything that varies between agents reaches the widget without one: theme and branding
 * through `updateConfig`, the conversation through `setMessages`, and `run_url` off `propsRef`
 * when a callback fires. The rest of the config is the same for every agent, so there is nothing
 * left that only a mount could deliver - and a remount would throw away the conversation and the
 * composer draft to deliver it.
 */
export function GooeyEmbedPreview(
  props: CustomComponentProps & {
    config: Record<string, any>;
    messages?: Array<Record<string, any>> | null;
    run_url: string;
    className?: string;
    style?: Record<string, string | number>;
  }
) {
  const { config, messages, className, style } = props;
  const propsRef = useRef(props);
  propsRef.current = props;

  const controllerRef = useRef<any>(null);
  const mountedRef = useRef(false);

  useEffect(() => {
    const loadEmbed = () => {
      const GooeyEmbed = window.GooeyEmbed;
      if (!GooeyEmbed || mountedRef.current) return;

      const embedTarget = document.getElementById("gooey-embed");
      if (!embedTarget) return;

      const sendMessage = (payload: unknown) => {
        const btn = document.getElementById(
          "onSendMessage"
        ) as HTMLInputElement | null;
        if (!btn) return;
        btn.value = JSON.stringify(payload);
        btn.click();
      };

      controllerRef.current = {
        messages: propsRef.current.messages,
        onSendMessage: sendMessage,
        onEditQuery: (_messageId: string, input_data: any, webUrl?: string) => {
          // webUrl identifies the run that produced the edited turn, so the
          // server re-runs that turn rather than always the latest one
          if (!webUrl) return;
          sendMessage({ ...input_data, edit_run_url: webUrl });
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
      mountedRef.current = true;
    };

    // the lib is a plain <script> tag, so it may not have run yet on a cold load
    const script = document.getElementById("gooey-embed-script");
    script?.addEventListener("load", loadEmbed);
    loadEmbed();

    return () => {
      script?.removeEventListener("load", loadEmbed);
      mountedRef.current = false;
      controllerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
