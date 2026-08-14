import clsx from "clsx";
import { useEffect, useRef, useState } from "react";

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
    login_uri?: string;
    auto_select?: boolean;
    cancel_on_tap_outside?: boolean;
    itp_support?: boolean;
    ux_mode?: "popup" | "redirect";
    use_fedcm_for_button?: boolean;
    context?: string;
    error_callback?: (error: { type?: string; message?: string }) => void;
  }) => void;
  renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
  prompt: () => void;
  disableAutoSelect: () => void;
};

declare global {
  interface Window {
    google?: { accounts: { id: GsiId } };
    GOOGLE_CLIENT_ID?: string;
    handleCredentialResponse?: (response: GsiCredentialResponse) => void;
    waitUntilHydrated?: Promise<void>;
    getGsiLoginUri?: () => string;
    shouldUseRedirectSignIn?: () => boolean;
    startGoogleRedirectSignIn?: () => Promise<void>;
  }
}

const GSI_CLIENT_SRC = "https://accounts.google.com/gsi/client";
const GSI_SCRIPT_ID = "google-gsi-client";

let gsiClientPromise: Promise<void> | null = null;
let gsiInitialized = false;
let oneTapPrompted = false;

export function GoogleSignInButton({ compact }: { compact: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [useRedirectButton, setUseRedirectButton] = useState(false);

  useEffect(() => {
    // iOS cannot finish a GSI/Firebase popup: after the user clicks their
    // account, Google tries to return via storagerelay:// and shows 400.
    // Use Firebase's https redirect handler instead of the GSI iframe.
    if (isIosUserAgent()) {
      setUseRedirectButton(true);
      return;
    }
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

  if (useRedirectButton) {
    return (
      <button
        type="button"
        data-replace-login-spinner
        data-submit-disabled
        className={clsx(
          "nav-google-signin btn btn-light border d-flex align-items-center justify-content-center gap-2",
          compact ? "p-2" : "w-100"
        )}
        onClick={() => window.startGoogleRedirectSignIn?.()}
        title="Continue with Google"
      >
        <i className="fa-brands fa-google" aria-hidden="true" />
        {!compact && <span>Continue with Google</span>}
      </button>
    );
  }

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
    //
    // iOS turns the GSI popup into a full-page Google visit. Completing
    // that with storagerelay:// (popup default) 400s after the user clicks
    // their account. Redirect POSTs the ID token to /login/ instead.
    stashLoginNext();
    const useRedirect =
      window.shouldUseRedirectSignIn?.() || isIosUserAgent();
    gsiId.initialize({
      client_id: clientId,
      callback: (response) => window.handleCredentialResponse?.(response),
      login_uri: window.getGsiLoginUri?.() || `${window.location.origin}/login/`,
      auto_select: false,
      cancel_on_tap_outside: true,
      itp_support: true,
      ux_mode: useRedirect ? "redirect" : "popup",
      use_fedcm_for_button: false,
      context: "signin",
      error_callback: (error) => {
        console.warn("Google sign-in error", error);
      },
    });
    gsiId.disableAutoSelect();
    gsiInitialized = true;
  }
  return true;
}

function isIosUserAgent() {
  return /iP(hone|ad|od)/.test(navigator.userAgent || "");
}

function stashLoginNext() {
  try {
    const path =
      window.location.pathname + window.location.search + window.location.hash;
    if (path && path !== "/login/" && !path.startsWith("/login/")) {
      sessionStorage.setItem("gooey_login_next", path);
    }
  } catch {
    return;
  }
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
