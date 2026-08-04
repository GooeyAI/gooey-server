import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useNavigate } from "@remix-run/react";
import { fetchServerAPI } from "~/fetchServerAPI";
import type { CustomComponentProps } from "~/components";

type AskGooeyNewProps = CustomComponentProps & {
  title?: string;
  highlight?: string;
  placeholder?: string;
};

export function AskGooeyNew({
  title = "What will you build today?",
  highlight = "",
  placeholder = "Ask Gooey to build an agent for farmers in Kenya",
}: AskGooeyNewProps) {
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [value, setValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showScrollArrow, setShowScrollArrow] = useState(true);

  const checkScroll = () => {
    if (scrollContainerRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = scrollContainerRef.current;
      setShowScrollArrow(scrollLeft + clientWidth < scrollWidth - 1);
    }
  };

  useEffect(() => {
    autoResize(textareaRef.current);
  }, [value]);

  useEffect(() => {
    checkScroll();
    window.addEventListener("resize", checkScroll);
    return () => window.removeEventListener("resize", checkScroll);
  }, []);

  const submit = async () => {
    const prompt = value.trim();
    if (!prompt || isSubmitting) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const redirectUrl = await fetchServerAPI<string | null>(
        "/__/gooey-builder/send-message",
        {
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

  const suggestions = [
    "Swahili WhatsApp bot for community health workers",
    "Which AI models best understand Hausa?",
    "Eval models using google sheet of audi...",
  ];

  return (
    <div
      style={{
        width: "100%",
        minHeight: "75vh",
        padding: "48px 24px",
        background: "#FFFFFF",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          maxWidth: "840px",
          width: "100%",
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "28px",
        }}
      >
        <div
          className="d-flex align-items-center justify-content-center"
          style={{ gap: "16px", color: "#1f1f1f", marginBottom: "8px" }}
        >
          <img 
            src="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/47e069e2-5b65-11f1-80ef-02420a00016f/gooey-builder-logo-fit.gif" 
            alt="Gooey Logo" 
            style={{ width: "64px", height: "64px" }} 
          />
          <h1
            style={{
              margin: 0,
              textAlign: "center",
              fontSize: "3.2rem",
              fontWeight: 400,
              fontFamily: "Georgia, serif",
              color: "#111",
              letterSpacing: "-0.02em",
            }}
          >
            {titleParts}
          </h1>
        </div>

        <div
          style={{
            position: "relative",
            width: "100%",
            borderRadius: "16px",
            padding: "1px", // For the gradient border
            background: "linear-gradient(135deg, #5EE6D0 0%, #B7C8FE 50%, #E3E0F9 100%)",
            boxShadow: isFocused
              ? "0 0 10px rgba(94, 230, 208, 0.5)"
              : "0 0 6px rgba(94, 230, 208, 0.3)",
            transition: "box-shadow 0.15s ease",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div
            style={{
              width: "100%",
              background: "rgba(255, 255, 255, 0.99)",
              borderRadius: "15.5px",
              padding: "16px 8px 8px 16px",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
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
              rows={1}
              disabled={isSubmitting}
              aria-label={title}
              style={{
                width: "100%",
                minHeight: "24px",
                maxHeight: "240px",
                background: "transparent",
                border: "none",
                outline: "none",
                color: "#4B587A",
                fontSize: "14px",
                lineHeight: "20px",
                resize: "none",
                padding: "0",
                fontFamily: "'Inter', sans-serif",
              }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", height: "36px" }}>
              <button
                type="button"
                style={{
                  background: "none",
                  border: "none",
                  padding: "5px",
                  color: "#000",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "24px",
                  height: "24px",
                  borderRadius: "8px",
                }}
              >
                <i className="fa-regular fa-plus" style={{ fontSize: "14px" }} />
              </button>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <button
                  type="button"
                  style={{
                    background: "none",
                    border: "none",
                    padding: "0",
                    color: "#0A1021",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "32px",
                    height: "32px",
                  }}
                >
                  <i className="fa-regular fa-microphone" style={{ fontSize: "16px" }} />
                </button>
                <button
                  type="button"
                  data-submit-disabled
                  onClick={submit}
                  disabled={!canSubmit}
                  aria-label="Send message"
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "12px",
                    background: canSubmit ? "#e0e0e0" : "#D9D9D9",
                    border: "none",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: canSubmit ? "#333" : "#8994B1",
                    cursor: canSubmit ? "pointer" : "not-allowed",
                    transition: "background 0.2s ease, color 0.2s ease",
                  }}
                >
                  {isSubmitting ? (
                    <i
                      className="fa-regular fa-spinner-third fa-spin"
                      style={{ fontSize: "16px" }}
                    />
                  ) : (
                    <i
                      className="fa-solid fa-arrow-up"
                      style={{ fontSize: "16px" }}
                    />
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div style={{ position: "relative", width: "100%" }}>
          <div 
            id="suggestions-container"
            ref={scrollContainerRef}
            onScroll={checkScroll}
            style={{ 
              display: "flex", 
              gap: "12px", 
              width: "100%", 
              overflowX: "auto", 
              paddingBottom: "4px",
              alignItems: "center",
              scrollbarWidth: "none",
              msOverflowStyle: "none",
            }}
          >
            {suggestions.map((chip, i) => (
              <button
                key={i}
                onClick={() => setValue(chip)}
                style={{
                  background: "#fff",
                  border: "1px solid #eaeaea",
                  borderRadius: "16px",
                  padding: "6px 12px",
                  fontSize: "13px",
                  color: "#000",
                  whiteSpace: "nowrap",
                  cursor: "pointer",
                  transition: "background 0.2s ease",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#f9f9f9")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "#fff")}
              >
                {chip}
              </button>
            ))}
          </div>
          {showScrollArrow && (
            <div
              style={{
                position: "absolute",
                right: 0,
                top: 0,
                bottom: "4px",
                width: "80px",
                background: "linear-gradient(to right, rgba(255,255,255,0) 0%, rgba(255,255,255,1) 60%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "flex-end",
                pointerEvents: "none",
              }}
            >
              <button
                onClick={() => {
                  if (scrollContainerRef.current) scrollContainerRef.current.scrollBy({ left: 250, behavior: "smooth" });
                }}
                style={{
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  padding: "8px 4px 8px 16px",
                  color: "#000",
                  pointerEvents: "auto",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <i className="fa-solid fa-chevron-right" style={{ fontSize: "14px" }} />
              </button>
            </div>
          )}
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
