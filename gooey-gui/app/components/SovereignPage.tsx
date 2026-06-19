import { useEffect } from "react";
import type { CustomComponentProps } from "~/components";

const SOVEREIGN_HTML_URL = "/static/sovereign/sovereign.html";

export function SovereignPage(_props: CustomComponentProps) {
  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
    };
  }, []);

  return (
    <iframe
      title="How Middle Powers Cooperate for AI Sovereignty"
      src={SOVEREIGN_HTML_URL}
      style={{
        border: "none",
        display: "block",
        height: "100vh",
        left: 0,
        margin: 0,
        padding: 0,
        position: "fixed",
        top: 0,
        width: "100vw",
        zIndex: 9999,
      }}
    />
  );
}
