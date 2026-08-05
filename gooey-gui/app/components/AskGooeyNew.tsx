import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useNavigate } from "@remix-run/react";
import { fetchServerAPI } from "~/fetchServerAPI";
import { useLiveTranscription } from "~/useLiveTranscription";
import type { CustomComponentProps } from "~/components";

type AskGooeyNewProps = CustomComponentProps & {
  title?: string;
  highlight?: string;
  placeholder?: string;
};

type Attachment = {
  id: string;
  name: string;
  contentType: string;
  url: string | null;
  uploading: boolean;
};

export function AskGooeyNew({
  title = "What will you build today?",
  highlight = "",
  placeholder = "Ask Gooey to build an agent for farmers in Kenya",
}: AskGooeyNewProps) {
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showScrollArrow, setShowScrollArrow] = useState(true);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const { micState, toggleRecording, stopRecording } = useLiveTranscription({
    value,
    setValue,
    setError,
  });

  const onFilesSelected = async (files: FileList | null) => {
    if (!files || !files.length) return;
    setError(null);
    for (const file of Array.from(files)) {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setAttachments((prev) => [
        ...prev,
        {
          id,
          name: file.name,
          contentType: file.type,
          url: null,
          uploading: true,
        },
      ]);
      try {
        const url = await uploadFile(file);
        setAttachments((prev) =>
          prev.map((a) => {
            if (a.id === id) return { ...a, url, uploading: false };
            return a;
          })
        );
      } catch (err) {
        console.error(err);
        setAttachments((prev) => prev.filter((a) => a.id !== id));
        setError(
          err instanceof Error ? err.message : "Upload failed. Try again."
        );
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

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

  const isUploading = attachments.some((a) => a.uploading);

  const submit = async () => {
    const prompt = value.trim();
    if (!prompt || isSubmitting || isUploading) return;
    stopRecording();
    setIsSubmitting(true);
    setError(null);
    const inputImages = [];
    const inputDocuments = [];
    for (const a of attachments) {
      if (!a.url) continue;
      if (a.contentType.startsWith("image/")) {
        inputImages.push(a.url);
      } else {
        inputDocuments.push(a.url);
      }
    }
    try {
      const redirectUrl = await fetchServerAPI<string | null>(
        "/__/gooey-builder/send-message",
        {
          input_data: {
            input_prompt: prompt,
            input_images: inputImages,
            input_documents: inputDocuments,
          },
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

  const canSubmit = value.trim().length > 0 && !isSubmitting && !isUploading;
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
            {attachments.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                {attachments.map((a) => (
                  <div
                    key={a.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                      background: "#F4F5F7",
                      border: "1px solid #eaeaea",
                      borderRadius: "10px",
                      padding: "4px 8px",
                      fontSize: "12px",
                      color: "#333",
                      maxWidth: "260px",
                    }}
                  >
                    {a.uploading ? (
                      <i
                        className="fa-regular fa-spinner-third fa-spin"
                        style={{ fontSize: "12px" }}
                      />
                    ) : (
                      <i
                        className={
                          a.contentType.startsWith("image/")
                            ? "fa-regular fa-image"
                            : "fa-regular fa-file"
                        }
                        style={{ fontSize: "12px" }}
                      />
                    )}
                    <span
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {a.name}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeAttachment(a.id)}
                      aria-label={`Remove ${a.name}`}
                      style={{
                        background: "none",
                        border: "none",
                        padding: "0",
                        cursor: "pointer",
                        color: "#888",
                        display: "flex",
                        alignItems: "center",
                      }}
                    >
                      <i className="fa-regular fa-xmark" style={{ fontSize: "12px" }} />
                    </button>
                  </div>
                ))}
              </div>
            )}
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
                color: value ? "#000" : "#4B587A",
                fontSize: "14px",
                lineHeight: "20px",
                resize: "none",
                padding: "0",
                fontFamily: "'Inter', sans-serif",
              }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", height: "36px" }}>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={(e) => onFilesSelected(e.target.files)}
                style={{ display: "none" }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isSubmitting}
                aria-label="Attach files"
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
                  onClick={toggleRecording}
                  disabled={isSubmitting || micState === "connecting"}
                  aria-label={
                    micState === "recording"
                      ? "Stop dictation"
                      : "Dictate with microphone"
                  }
                  style={{
                    background: micState === "recording" ? "#FDECEC" : "none",
                    border: "none",
                    padding: "0",
                    color: micState === "recording" ? "#DC3545" : "#0A1021",
                    cursor:
                      micState === "connecting" ? "not-allowed" : "pointer",
                    opacity: micState === "connecting" ? 0.6 : 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "32px",
                    height: "32px",
                    borderRadius: "8px",
                    transition: "background 0.2s ease, color 0.2s ease",
                  }}
                >
                  {micState === "connecting" ? (
                    <i
                      className="fa-regular fa-spinner-third fa-spin"
                      style={{ fontSize: "16px" }}
                    />
                  ) : (
                    <i
                      className={
                        micState === "recording"
                          ? "fa-solid fa-microphone fa-beat-fade"
                          : "fa-regular fa-microphone"
                      }
                      style={{ fontSize: "16px" }}
                    />
                  )}
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

async function uploadFile(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/__/file-upload/", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Upload failed with status ${response.status}`);
  }
  const data = (await response.json()) as { url: string };
  return data.url;
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
