import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useNavigate } from "@remix-run/react";
import { fetchServerAPI } from "~/fetchServerAPI";
import type { CustomComponentProps } from "~/components";

type ExploreBuilderPromptProps = CustomComponentProps & {
  workflow_url: string;
  title?: string;
  highlight?: string;
  placeholder?: string;
};

export function ExploreBuilderPrompt({
  workflow_url,
  title = "What do you want to build today?",
  highlight = "build",
  placeholder = "India stock market today",
}: ExploreBuilderPromptProps) {
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [value, setValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    autoResize(textareaRef.current);
  }, [value]);

  const submit = async () => {
    const prompt = value.trim();
    if (!prompt || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const redirectUrl = await fetchServerAPI<string | null>(
        "/__/gooey-builder/send-message",
        {
          workflow_url,
          input_data: { input_prompt: prompt },
        }
      );
      if (!redirectUrl) {
        setIsSubmitting(false);
        return;
      }
      const url = new URL(redirectUrl);
      navigate(url.pathname + url.search);
    } catch (err) {
      console.error(err);
      setError(
        err instanceof Error ? err.message : "Something went wrong. Try again."
      );
      setIsSubmitting(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const canSubmit = value.trim().length > 0 && !isSubmitting;
  const titleParts = renderTitleWithHighlight(title, highlight);

  return (
    <div
      style={{
        width: "100%",
        minHeight: "75vh",
        padding: "48px 24px",
        background:
          "linear-gradient(180deg, #FFFFFF 0%, #FFFFFF 18%, #F4FFFB 55%, #DFFCF1 100%)",
        borderBottom: "1px solid #CFE9DD",
        borderRadius: "0 0 16px 16px",
        marginBottom: "8px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          maxWidth: "720px",
          width: "100%",
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "28px",
        }}
      >
        <div
          className="d-flex align-items-center"
          style={{ gap: "10px", color: "#1f1f1f" }}
        >
          <i
            className="fa-solid fa-sparkles"
            style={{ color: "#000", fontSize: "1.1rem" }}
            aria-hidden="true"
          />
          <h1
            style={{
              margin: 0,
              textAlign: "center",
              fontSize: "1.65rem",
              fontWeight: 600,
              letterSpacing: "-0.01em",
              color: "#111",
            }}
          >
            {titleParts}
          </h1>
        </div>

        <div
          style={{
            position: "relative",
            width: "100%",
            background: "#fff",
            border: `1px solid ${isFocused ? "#111" : "#d8d8d8"}`,
            boxShadow: isFocused
              ? "0 6px 24px rgba(0,0,0,0.08)"
              : "0 2px 10px rgba(0,0,0,0.04)",
            borderRadius: "22px",
            padding: "16px 56px 14px 20px",
            transition: "border-color 0.15s ease, box-shadow 0.15s ease",
          }}
        >
          <textarea
            ref={textareaRef}
            data-submit-disabled
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder={placeholder}
            rows={2}
            disabled={isSubmitting}
            aria-label={title}
            style={{
              width: "100%",
              minHeight: "52px",
              maxHeight: "240px",
              background: "transparent",
              border: "none",
              outline: "none",
              color: "#111",
              fontSize: "1rem",
              lineHeight: 1.5,
              resize: "none",
              padding: 0,
              fontFamily: "inherit",
            }}
          />
          <button
            type="button"
            data-submit-disabled
            onClick={submit}
            disabled={!canSubmit}
            aria-label="Send message"
            className="btn btn-theme p-0 m-0"
            style={{
              position: "absolute",
              right: "10px",
              bottom: "10px",
              width: "34px",
              height: "34px",
              minWidth: "34px",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: canSubmit ? 1 : 0.45,
              cursor: canSubmit ? "pointer" : "not-allowed",
              fontWeight: "normal",
            }}
          >
            {isSubmitting ? (
              <i
                className="fa-regular fa-spinner-third fa-spin"
                style={{ fontSize: "0.95rem" }}
              />
            ) : (
              <i
                className="fa-solid fa-arrow-up"
                style={{ fontSize: "0.95rem" }}
              />
            )}
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="text-danger"
            style={{ textAlign: "center", fontSize: "0.9rem" }}
          >
            {error}
          </div>
        )}
      </div>
    </div>
  );
}

function renderTitleWithHighlight(title: string, highlight: string) {
  if (!highlight) return title;
  const lower = title.toLowerCase();
  const idx = lower.indexOf(highlight.toLowerCase());
  if (idx === -1) return title;
  const before = title.slice(0, idx);
  const match = title.slice(idx, idx + highlight.length);
  const after = title.slice(idx + highlight.length);
  return (
    <>
      {before}
      <span
        style={{
          backgroundColor: "#A5FFEE",
          padding: "0 4px",
          borderRadius: "4px",
        }}
      >
        {match}
      </span>
      {after}
    </>
  );
}

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
}
