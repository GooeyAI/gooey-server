import { useEffect } from "react";
import type { CustomComponentProps } from "~/components";

/**
 * Removes the chat preview when its tab goes away.
 *
 * GooeyEmbed does not render into `#gooey-embed`. It creates its own host element - a
 * `<div style="display: contents">` carrying an open shadow root - and appends it as a
 * sibling inside whatever container was on screen. React never created that node, so
 * reconciliation leaves it behind: navigate Preview -> Config client-side and the widget is
 * still there, stranded under the Config content. `display: contents` is why it spans the
 * full width rather than staying in the column it came from.
 *
 * `GooeyEmbed.unmount()` is not usable here - it takes no target and would tear down the
 * Builder too, since both share one global instance. So this removes the host node itself,
 * identified by the `.gooey-embed-container` inside its shadow root, and deliberately skips
 * anything under `#gooey-builder-embed` so the Builder is never touched.
 *
 * Renders nothing: it exists only for the unmount hook, which React runs exactly when the
 * preview's tab is navigated away from.
 */
export function GooeyEmbedTeardown({}: CustomComponentProps) {
  useEffect(() => {
    return () => {
      document.querySelectorAll("div").forEach((el) => {
        const shadow = (el as HTMLElement & { shadowRoot?: ShadowRoot | null })
          .shadowRoot;
        if (!shadow?.querySelector(".gooey-embed-container")) return;
        // the Builder owns its own embed and stays mounted across tabs
        if (el.closest("#gooey-builder-embed")) return;
        el.remove();
      });
    };
  }, []);

  return null;
}
