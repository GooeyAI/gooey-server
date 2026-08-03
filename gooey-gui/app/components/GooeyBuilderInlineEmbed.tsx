import { useEffect, useRef } from "react";
import { fetchServerAPI } from "~/fetchServerAPI";
import type { CustomComponentProps } from "~/components";
import { useGlobalContext } from "~/globalContext";

declare global {
  interface Window {
    GooeyEmbed?: any;
  }
}

export function GooeyBuilderInlineEmbed(
  props: CustomComponentProps & {
    config: Record<string, any>;
    sidebar_key: string;
    messages?: Record<string, any>[] | null;
    builder_run_url: string;
    workflow_state: Record<string, any>;
  }
) {
  const { config, messages } = props;
  const propsRef = useRef(props);
  propsRef.current = props;

  const controllerRef = useRef<any>(null);

  const ctx = useGlobalContext();

  useEffect(() => {
    const loadEmbed = () => {
      const GooeyEmbed = window.GooeyEmbed;
      if (!GooeyEmbed) return;

      const embedTarget = document.getElementById("gooey-builder-embed");
      if (embedTarget?.children.length) {
        controllerRef.current?.setMessages?.(messages);
        return;
      }

      config.onClose = function () {
        window.dispatchEvent(
          new CustomEvent(`${propsRef.current.sidebar_key}:close`)
        );
      };

      controllerRef.current = {
        messages,
        onSendMessage: async (input_data: any) => {
          let redirectUrl = await fetchServerAPI<string | null>(
            "/__/gooey-builder/send-message",
            {
              workflow_url: window.location.href,
              builder_run_url: propsRef.current.builder_run_url,
              workflow_state: propsRef.current.workflow_state,
              input_data,
            }
          );
          if (!redirectUrl) return;
          let url = new URL(redirectUrl);
          ctx.current.navigate(url.pathname + url.search);
        },
        editQuery: (messageId: string, input_data: any) => {
          const payload = createEditedMessagePayload(
            propsRef.current.messages,
            messageId,
            input_data
          );
          if (!payload) return;
          controllerRef.current?.onSendMessage(payload);
        },
        onNewConversation: async () => {
          ctx.current.update_session_state({ builderOnNewConversation: true });
        },
        fetchConversations: () =>
          fetchServerAPI("/__/gooey-builder/fetch-conversations", {
            run_url: propsRef.current.builder_run_url,
          }),
        rerun: async (run_url: string) => {
          let redirectUrl = await fetchServerAPI<string | null>(
            "/__/gooey-builder/send-message",
            {
              workflow_url: window.location.href,
              builder_run_url: run_url,
              workflow_state: propsRef.current.workflow_state,
            }
          );
          if (!redirectUrl) return;
          let url = new URL(redirectUrl);
          ctx.current.navigate(url.pathname + url.search);
        },
      };

      GooeyEmbed.mount(config, controllerRef.current);
    };

    const script = document.getElementById("gooey-embed-script");
    script?.addEventListener("load", loadEmbed);
    loadEmbed();

    return () => {
      script?.removeEventListener("load", loadEmbed);
    };
  }, []);

  useEffect(() => {
    controllerRef.current?.setMessages?.(messages);
  }, [messages]);

  return <div className="w-100 h-100" id="gooey-builder-embed" />;
}

function createEditedMessagePayload(
  messages: Record<string, any>[] | null | undefined,
  messageId: string,
  inputData: Record<string, any>
) {
  const messageIndex = parseWidgetMessageIndex(messageId);
  if (messageIndex === null || !Array.isArray(messages)) return;
  if (messageIndex >= messages.length) return;

  return { ...inputData, messages: messages.slice(0, messageIndex) };
}

function parseWidgetMessageIndex(messageId: string): number | null {
  const prefix = "simple-msg-id-";
  if (!messageId.startsWith(prefix)) return null;

  const messageIndex = Number(messageId.slice(prefix.length));
  if (!Number.isInteger(messageIndex) || messageIndex < 0) return null;
  return messageIndex;
}
