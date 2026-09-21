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
    messages?: Record<string, any>[] | null;
    builder_run_url: string;
    workflow_state: Record<string, any>;
    builder_only?: boolean;
    /** Each prompt carries where an anonymous click goes; `login_url` is null when signed in. */
    prompts?: { text: string; login_url?: string | null }[];
    /** Set only for a logged-out visitor: the send endpoint is login-required. */
    login_url?: string | null;
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
          // Anonymous: the endpoint is login-required, so sign in rather than 401.
          if (propsRef.current.login_url) {
            window.location.href = propsRef.current.login_url;
            return;
          }
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
        onEditQuery: (_messageId: string, input_data: any, webUrl?: string) => {
          // webUrl identifies the run that produced the edited turn, so the
          // server re-runs that turn rather than always the latest one
          if (!webUrl) return;
          controllerRef.current?.onSendMessage({
            ...input_data,
            edit_run_url: webUrl,
          });
        },
        onNewConversation: async () => {
          ctx.current.update_session_state({ builderOnNewConversation: true });
        },
        rerun: async (run_url: string) => {
          if (propsRef.current.login_url) {
            window.location.href = propsRef.current.login_url;
            return;
          }
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
    const rerunEvent = `${propsRef.current.event_key}:rerun`;
    const onRerun = () =>
      controllerRef.current?.rerun?.(propsRef.current.builder_run_url);
    window.addEventListener(newConversationEvent, onNewConversation);
    window.addEventListener(rerunEvent, onRerun);

    return () => {
      script?.removeEventListener("load", loadEmbed);
      window.removeEventListener(newConversationEvent, onNewConversation);
      window.removeEventListener(rerunEvent, onRerun);
    };
  }, []);

  useEffect(() => {
    controllerRef.current?.setMessages?.(messages);
  }, [messages]);

  useEffect(() => {
    // A prompt carried back from login. Cleared first so a reload cannot re-send it.
    if (propsRef.current.login_url) return;
    const params = new URLSearchParams(window.location.search);
    const prompt = params.get("builderprompt");
    if (!prompt) return;
    params.delete("builderprompt");
    const search = params.toString();
    window.history.replaceState(
      {},
      "",
      window.location.pathname + (search ? `?${search}` : "")
    );
    controllerRef.current?.onSendMessage?.({ input_prompt: prompt });
  }, []);

  const prompts = props.prompts ?? [];
  return (
    <>
      {!!prompts.length && (
        <div className="v2-builder-prompts">
          {prompts.map((s) =>
            s.login_url ? (
              // Logged out: the prompt rides inside login's `next` and replays on return.
              <a key={s.text} className="v2-builder-prompt" href={s.login_url}>
                {s.text}
              </a>
            ) : (
              <button
                key={s.text}
                type="button"
                className="v2-builder-prompt"
                onClick={() =>
                  controllerRef.current?.onSendMessage?.({ input_prompt: s.text })
                }
              >
                {s.text}
              </button>
            )
          )}
        </div>
      )}
      <div id="gooey-builder-embed" />
    </>
  );
}
