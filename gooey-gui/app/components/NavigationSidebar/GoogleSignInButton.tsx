import clsx from "clsx";
import { useEffect, useRef } from "react";

// Google Identity Services (GSI) sign-in button for anonymous users, mirroring
// the old templates/google_one_tap_button.html behaviour that lived in the
// header. The page shell (templates/login_scripts.html + static/js/auth.js)
// already wires up `window.GOOGLE_CLIENT_ID` and the global
// `handleCredentialResponse` callback for anonymous users; here we lazy-load
// the GSI client, initialize it once, and render a button into each container.

type GsiCredentialResponse = { credential: string };

type GsiId = {
  initialize: (config: {
    client_id: string;
    callback: (response: GsiCredentialResponse) => void;
  }) => void;
  renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
  prompt: () => void;
};

declare global {
  interface Window {
    google?: { accounts: { id: GsiId } };
    GOOGLE_CLIENT_ID?: string;
    handleCredentialResponse?: (response: GsiCredentialResponse) => void;
    waitUntilHydrated?: Promise<void>;
  }
}

const GSI_CLIENT_SRC = "https://accounts.google.com/gsi/client";
const GSI_SCRIPT_ID = "google-gsi-client";

let gsiClientPromise: Promise<void> | null = null;
let gsiInitialized = false;
let oneTapPrompted = false;

export function GoogleSignInButton({ compact }: { compact: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const setup = async () => {
      // Wait for hydration so the inline login scripts (which set
      // window.GOOGLE_CLIENT_ID) have run, then load the GSI client.
      await window.waitUntilHydrated;
      await loadGsiClient();
      if (cancelled) return;
      renderGsiButton(containerRef.current, compact);
    };
    // Swallow load/init failures: the footer keeps its "Sign In" link fallback.
    setup().catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [compact]);

  return (
    <div
      ref={containerRef}
      data-replace-login-spinner
      className={clsx("nav-google-signin d-flex justify-content-center")}
    />
  );
}

function renderGsiButton(container: HTMLElement | null, compact: boolean) {
  if (!container || !initGsi()) return;
  // Clear a button left over from a previous render (e.g. when `compact` flips
  // between the collapsed rail and expanded rail).
  container.innerHTML = "";
  window.google!.accounts.id.renderButton(
    container,
    compact
      ? { type: "icon", shape: "square", size: "large" }
      : {
          text: "continue_with",
          shape: "rectangular",
          size: "large",
          width: 200,
        }
  );
  if (!oneTapPrompted) {
    oneTapPrompted = true;
    window.google!.accounts.id.prompt();
  }
}

function initGsi(): boolean {
  const clientId = window.GOOGLE_CLIENT_ID;
  const gsiId = window.google?.accounts?.id;
  if (!clientId || !gsiId) return false;
  if (!gsiInitialized) {
    // Resolve the callback lazily so init doesn't race auth.js loading; by the
    // time a user completes sign-in, handleCredentialResponse is defined.
    gsiId.initialize({
      client_id: clientId,
      callback: (response) => window.handleCredentialResponse?.(response),
    });
    gsiInitialized = true;
  }
  return true;
}

function loadGsiClient(): Promise<void> {
  if (gsiClientPromise) return gsiClientPromise;
  gsiClientPromise = new Promise<void>((resolve, reject) => {
    if (window.google?.accounts?.id) return resolve();
    const existing = document.getElementById(GSI_SCRIPT_ID);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => {
        gsiClientPromise = null;
        reject(new Error("Failed to load Google Identity Services"));
      });
      return;
    }
    const script = document.createElement("script");
    script.id = GSI_SCRIPT_ID;
    script.src = GSI_CLIENT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => {
      gsiClientPromise = null;
      reject(new Error("Failed to load Google Identity Services"));
    };
    document.head.appendChild(script);
  });
  return gsiClientPromise;
}
