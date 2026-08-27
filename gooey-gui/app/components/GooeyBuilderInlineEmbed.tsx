import { useEffect, useRef } from "react";
import { fetchServerAPI } from "~/fetchServerAPI";
import type { CustomComponentProps } from "~/components";
import { useGlobalContext } from "~/globalContext";
import { useAppShellPanelActions } from "~/appShellContext";

declare global {
  interface Window {
    GooeyEmbed?: any;
  }
}

export function GooeyBuilderInlineEmbed(
  props: CustomComponentProps & {
    config: Record<string, any>;
    event_key: string;
    messages?: Record<string, any> | null;
    builder_run_url: string;
    workflow_state: Record<string, any>;
    builder_only?: boolean;
  }
) {
  const { config, messages } = props;
  const propsRef = useRef(props);
  propsRef.current = props;

  const controllerRef = useRef<any>(null);

  const ctx = useGlobalContext();
  const { setPanelOpen } = useAppShellPanelActions();

  useEffect(() => {
    const loadEmbed = () => {
      const GooeyEmbed = window.GooeyEmbed;
      if (!GooeyEmbed) return;

      const embedTarget = document.getElementById("gooey-builder-embed");
      if (embedTarget?.children.length) {
        controllerRef.current?.setMessages?.(messages);
        return;
      }

      // builder-only pages are standalone, so there's no sidebar to close
      if (!propsRef.current.builder_only) {
        config.onClose = function () {
          setPanelOpen(propsRef.current.event_key, false);
          window.dispatchEvent(
            new CustomEvent(`${propsRef.current.event_key}:close`)
          );
        };
      }

      controllerRef.current = {
        messages,
        onSendMessage: async (input_data: any) => {
          let redirectUrl = await fetchServerAPI<string | null>(
            "/__/gooey-builder/send-message",
            {
              // builder-only pages have no associated workflow to clone
              workflow_url: propsRef.current.builder_only
                ? null
                : window.location.href,
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
              workflow_url: propsRef.current.builder_only
                ? null
                : window.location.href,
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

    // v2 hides the widget's header, so the panel's title button fires this instead. Routed
    // through the controller, the same path the widget's own control uses.
    const newConversationEvent = `${propsRef.current.event_key}:new`;
    const onNewConversation = () =>
      controllerRef.current?.onNewConversation?.();
    window.addEventListener(newConversationEvent, onNewConversation);

    return () => {
      script?.removeEventListener("load", loadEmbed);
      window.removeEventListener(newConversationEvent, onNewConversation);
    };
  }, []);

  useEffect(() => {
    controllerRef.current?.setMessages?.(messages);
  }, [messages]);

  // No `w-100`: Bootstrap's width utilities are `!important` and would beat the settled-width
  // rule in app.css. Width is owned there.
  return <div className="h-100" id="gooey-builder-embed" />;
}
