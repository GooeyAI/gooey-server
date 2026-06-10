import * as Sentry from "@sentry/remix";
import type { KeyboardEvent } from "react";
import { useRef, useState } from "react";
import type { CustomComponentProps } from "~/components";
import { fetchServerAPI } from "~/fetchServerAPI";
import { InputLabel } from "~/gooeyInput";

export function ForgotPasswordForm({
  submitUrl,
  initialEmail,
}: CustomComponentProps & {
  submitUrl: string;
  initialEmail: string;
}) {
  const emailRef = useRef<HTMLInputElement>(null);
  const [email, setEmail] = useState(
    initialEmail.replace(/\s/g, "").toLowerCase()
  );
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canSubmit = email.length > 0;

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
        { email }
      );
      if (data.redirect) {
        window.location.assign(data.redirect);
        return;
      }
      setError(data.error || "Something went wrong. Please try again.");
    } catch (err) {
      console.error(err);
      Sentry.captureException(err);
      setError("Something went wrong. Please try again.");
    }
    setIsSubmitting(false);
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
      <h3 className="text-center mb-2">Reset password</h3>
      <p className="text-muted text-center mb-4">
        Enter your email to open the password reset form.
      </p>

      <div className="gui-input gui-input-text mb-4">
        <InputLabel label="##### Email" htmlFor="forgot-password-email" />
        <input
          ref={emailRef}
          id="forgot-password-email"
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
          <span
            className="spinner-border spinner-border-sm me-2"
            role="status"
            aria-hidden="true"
          />
        ) : (
          <i className="fa-solid fa-arrow-right me-2" aria-hidden="true" />
        )}
        Continue
      </button>
    </div>
  );
}
