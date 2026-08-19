import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { useNavigate } from "@remix-run/react";
import { fetchServerAPI } from "~/fetchServerAPI";
import { useLiveTranscription } from "~/useLiveTranscription";
import type { CustomComponentProps } from "~/components";
import "~/styles/gooey-orbit-border.css";
import "./AskGooeyNew.css";

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
  const inputBarClass = isFocused
    ? "ask-gooey-input-bar ask-gooey-input-bar--focused gooey-orbit-border gooey-orbit-border--strong"
    : "ask-gooey-input-bar gooey-orbit-border gooey-orbit-border--strong";
  const sendBtnClass = canSubmit
    ? "ask-gooey-send-btn ask-gooey-send-btn--active"
    : "ask-gooey-send-btn";
  const micBtnClass = micButtonClass(micState);

  const suggestions = [
    "Swahili WhatsApp bot for community health workers",
    "Which AI models best understand Hausa?",
    "Eval models using google sheet of audi...",
  ];

  return (
    <div className="ask-gooey-page">
      <div className="ask-gooey-column">
        <div className="ask-gooey-header">
          <img
            className="ask-gooey-logo"
            src="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/47e069e2-5b65-11f1-80ef-02420a00016f/gooey-builder-logo-fit.gif"
            alt="Gooey Logo"
          />
          <h1 className="ask-gooey-title">{titleParts}</h1>
        </div>

        <div className="ask-gooey-composer">
          {error && (
            <div role="alert" className="ask-gooey-error text-danger">
              {error}
            </div>
          )}
          <div className="ask-gooey-suggestions">
            <div
              id="suggestions-container"
              ref={scrollContainerRef}
              onScroll={checkScroll}
              className="ask-gooey-suggestions-scroll"
            >
              {suggestions.map((chip, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setValue(chip)}
                  className="ask-gooey-suggestion-chip"
                >
                  {chip}
                </button>
              ))}
            </div>
            {showScrollArrow && (
              <div className="ask-gooey-suggestions-fade">
                <button
                  type="button"
                  onClick={() => {
                    if (scrollContainerRef.current) {
                      scrollContainerRef.current.scrollBy({
                        left: 250,
                        behavior: "smooth",
                      });
                    }
                  }}
                  className="ask-gooey-suggestions-arrow"
                >
                  <i className="fa-solid fa-chevron-right" />
                </button>
              </div>
            )}
          </div>
          <div className={inputBarClass}>
            <div className="ask-gooey-input-bar-inner">
              {attachments.length > 0 && (
                <div className="ask-gooey-attachments">
                  {attachments.map((a) => (
                    <div key={a.id} className="ask-gooey-attachment">
                      {a.uploading ? (
                        <i className="fa-regular fa-spinner-third fa-spin" />
                      ) : (
                        <i
                          className={
                            a.contentType.startsWith("image/")
                              ? "fa-regular fa-image"
                              : "fa-regular fa-file"
                          }
                        />
                      )}
                      <span className="ask-gooey-attachment-name">{a.name}</span>
                      <button
                        type="button"
                        onClick={() => removeAttachment(a.id)}
                        aria-label={`Remove ${a.name}`}
                        className="ask-gooey-attachment-remove"
                      >
                        <i className="fa-regular fa-xmark" />
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
                className="ask-gooey-textarea"
              />
              <div className="ask-gooey-toolbar">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  onChange={(e) => onFilesSelected(e.target.files)}
                  className="ask-gooey-file-input"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isSubmitting}
                  aria-label="Attach files"
                  className="ask-gooey-attach-btn"
                >
                  <i className="fa-regular fa-plus" />
                </button>
                <div className="ask-gooey-toolbar-right">
                  <button
                    type="button"
                    onClick={toggleRecording}
                    disabled={isSubmitting || micState === "connecting"}
                    aria-label={
                      micState === "recording"
                        ? "Stop dictation"
                        : "Dictate with microphone"
                    }
                    className={micBtnClass}
                  >
                    {micState === "connecting" ? (
                      <i className="fa-regular fa-spinner-third fa-spin" />
                    ) : (
                      <i
                        className={
                          micState === "recording"
                            ? "fa-solid fa-microphone fa-beat-fade"
                            : "fa-regular fa-microphone"
                        }
                      />
                    )}
                  </button>
                  <button
                    type="button"
                    data-submit-disabled
                    onClick={submit}
                    disabled={!canSubmit}
                    aria-label="Send message"
                    className={sendBtnClass}
                  >
                    {isSubmitting ? (
                      <i className="fa-regular fa-spinner-third fa-spin" />
                    ) : (
                      <i className="fa-solid fa-arrow-up" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
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
      <span className="ask-gooey-title-highlight">{match}</span>
      {after}
    </>
  );
}

function micButtonClass(micState: string) {
  if (micState === "recording") {
    return "ask-gooey-mic-btn ask-gooey-mic-btn--recording";
  }
  if (micState === "connecting") {
    return "ask-gooey-mic-btn ask-gooey-mic-btn--connecting";
  }
  return "ask-gooey-mic-btn";
}

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
}
