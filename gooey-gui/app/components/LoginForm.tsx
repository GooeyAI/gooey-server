import * as Sentry from "@sentry/remix";
import type { KeyboardEvent } from "react";
import { useRef, useState } from "react";
import type { CustomComponentProps } from "~/components";
import { fetchServerAPI } from "~/fetchServerAPI";
import { InputLabel } from "~/gooeyInput";

type Mode = "signin" | "signup";

// the backend endpoint is the same for both modes (it signs up unknown
// emails automatically) -- the mode only changes the UI text
const COPY: Record<
  Mode,
  {
    title: string;
    submit: string;
    submitting: string;
    submitIcon: string;
    passwordAutoComplete: string;
    togglePrompt: string;
    toggleAction: string;
  }
> = {
  signin: {
    title: "Sign in to Gooey.AI",
    submit: "Sign in",
    submitting: "Signing in...",
    submitIcon: "fa-right-to-bracket",
    passwordAutoComplete: "current-password",
    togglePrompt: "New here?",
    toggleAction: "Sign up",
  },
  signup: {
    title: "Sign up for Gooey.AI",
    submit: "Create account",
    submitting: "Creating account...",
    submitIcon: "fa-user-plus",
    passwordAutoComplete: "new-password",
    togglePrompt: "Already have an account?",
    toggleAction: "Sign in",
  },
};

export function LoginForm({
  submitUrl,
  forgotPasswordUrl,
}: CustomComponentProps & {
  submitUrl: string;
  forgotPasswordUrl: string;
}) {
  const emailRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const copy = COPY[mode];
  const canSubmit = email.length > 0 && password.length > 0;

  const submit = async () => {
    if (!canSubmit || isSubmitting) return;
    // the surrounding gooey form is noValidate and we submit via fetch, so
    // trigger the email input's native browser validation ourselves
    if (emailRef.current && !emailRef.current.reportValidity()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const data = await fetchServerAPI<{ redirect?: string; error?: string }>(
        submitUrl,
        { email, password }
      );
      if (data.redirect) {
        window.location.assign(data.redirect);
        return;
      }
      setError(data.error || `${copy.submit} failed. Please try again.`);
    } catch (err) {
      console.error(err);
      Sentry.captureException(err);
      setError("Something went wrong. Please try again.");
    }
    setIsSubmitting(false);
  };

  const toggleMode = () => {
    if (mode === "signin") {
      setMode("signup");
    } else {
      setMode("signin");
    }
    setError(null);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) {
      // prevent the surrounding gooey form from submitting
      e.preventDefault();
      submit();
    }
  };

  return (
    <div
      className="bg-white border rounded-3 shadow-sm p-4 p-md-5 text-start w-100"
      style={{ maxWidth: "26rem" }}
    >
      <h3 className="text-center mb-2">{copy.title}</h3>
      <p className="text-muted text-center mb-4">
        Incredible Open Source, shared AI workflows
      </p>

      <div className="gui-input gui-input-text">
        <InputLabel label="##### Email" htmlFor="login-email" />
        <input
          ref={emailRef}
          id="login-email"
          type="email"
          required
          autoComplete="email"
          autoFocus
          data-submit-disabled
          disabled={isSubmitting}
          value={email}
          // disallow spaces and uppercase (typed or pasted) in the email
          onChange={(e) =>
            setEmail(e.target.value.replace(/\s/g, "").toLowerCase())
          }
          onKeyDown={onKeyDown}
        />
      </div>

      <div className="gui-input gui-input-password mb-4">
        <InputLabel label="##### Password" htmlFor="login-password" />
        <input
          id="login-password"
          type="password"
          autoComplete={copy.passwordAutoComplete}
          data-submit-disabled
          disabled={isSubmitting}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={onKeyDown}
        />
      </div>

      {error && (
        <div className="alert alert-danger py-2" role="alert">
          {error}
        </div>
      )}

      <button
        type="button"
        data-submit-disabled
        className="btn btn-theme btn-primary w-100 m-0"
        onClick={submit}
        disabled={!canSubmit || isSubmitting}
      >
        {isSubmitting ? (
          <>
            <span
              className="spinner-border spinner-border-sm me-2"
              role="status"
              aria-hidden="true"
            />
            {copy.submitting}
          </>
        ) : (
          <>
            <i
              className={`fa-solid ${copy.submitIcon} me-2`}
              aria-hidden="true"
            />
            {copy.submit}
          </>
        )}
      </button>

      <p className="text-muted text-center small mt-3 mb-0">
        {copy.togglePrompt}{" "}
        <button
          type="button"
          data-submit-disabled
          className="btn btn-link btn-sm p-0 m-0 align-baseline"
          onClick={toggleMode}
        >
          {copy.toggleAction}
        </button>
      </p>

      {mode === "signin" && (
        <p className="text-muted text-center small mt-1 mb-0">
          <a
            href={
              email
                ? `${forgotPasswordUrl}?email=${encodeURIComponent(email)}`
                : forgotPasswordUrl
            }
          >
            Forgot password?
          </a>
        </p>
      )}
    </div>
  );
}
