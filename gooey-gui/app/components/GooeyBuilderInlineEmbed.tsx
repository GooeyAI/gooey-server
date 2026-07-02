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
    messages?: Record<string, any> | null;
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
        onNewConversation: async () => {
          ctx.current.update_session_state({ builderOnNewConversation: true });
        },
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
