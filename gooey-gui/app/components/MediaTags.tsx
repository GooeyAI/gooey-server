import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom";
import { RenderedMarkdown } from "~/renderedMarkdown";
import { Link } from "@remix-run/react";

export function GooeyImg({
  src,
  caption,
  href,
  previewImg,
  enablePreviewDialog,
  ...props
}: React.ImgHTMLAttributes<HTMLImageElement> & {
  src: string;
  caption?: string;
  href?: string;
  previewImg?: string;
  enablePreviewDialog?: boolean;
}) {
  const [previewIsValid, onError] = useImageValid(previewImg);
  const [dialogOpen, setDialogOpen] = useState(false);

  let currentSrc;
  if (previewImg && previewIsValid) {
    currentSrc = previewImg;
  } else {
    currentSrc = src;
  }

  const clickable =
    enablePreviewDialog && !href && !currentSrc.startsWith("data:");

  const img = (
    <img
      className={"gui-img" + (clickable ? " gui-img-clickable" : "")}
      alt={caption}
      src={currentSrc}
      onError={onError}
      {...props}
      onClick={clickable ? () => setDialogOpen(true) : props.onClick}
    />
  );

  let child = (
    <>
      <RenderedMarkdown body={caption} />
      {clickable ? (
        <div
          className="gui-media-preview-wrap"
          style={{ position: "relative", maxWidth: 450 }}
        >
          {img}
          {/* Hover/cursor affordances (zoom-in cursor) aren't visible on
              touch devices, so show an explicit expand icon too - CSS fades
              it in on hover for mouse users, but keeps it always-on for
              touch (see .gui-media-expand-btn in app.css). */}
          <button
            aria-label="Expand image"
            title="Expand image"
            className="gui-media-expand-btn"
            onClick={() => setDialogOpen(true)}
            style={expandButtonStyle}
          >
            <i
              className="fa-solid fa-sm fa-up-right-and-down-left-from-center"
              aria-hidden="true"
            ></i>
          </button>
        </div>
      ) : (
        img
      )}
      {clickable && dialogOpen && (
        <MediaPreviewDialog onClose={() => setDialogOpen(false)} alt={caption}>
          <img src={src} alt={caption} style={mediaDialogStyle} />
        </MediaPreviewDialog>
      )}
    </>
  );

  if (href) {
    child = (
      <Link to={href}>
        <div>{child}</div>
      </Link>
    );
  }

  return child;
}

export function GooeyVideo({
  src,
  caption,
  previewImg,
  enablePreviewDialog,
  href,
  ...props
}: React.VideoHTMLAttributes<HTMLVideoElement> & {
  src: string;
  caption?: string;
  previewImg?: string;
  enablePreviewDialog?: boolean;
  href?: string;
}) {
  const [previewIsValid, onError] = useImageValid(previewImg);
  const [dialogOpen, setDialogOpen] = useState(false);

  const expandable = enablePreviewDialog && !href;

  let media;
  if (previewImg && previewIsValid) {
    media = (
      <img
        className="gui-video"
        src={previewImg}
        alt={caption}
        onError={onError}
      />
    );
  } else {
    media = (
      <video
        className="gui-video"
        {...props}
        // The dialog already offers a bigger view, so the inline player only
        // needs play/pause/seek/volume - hiding native fullscreen & PiP avoids
        // two competing "make this bigger" affordances sitting side by side.
        controlsList={expandable ? "nofullscreen noremoteplayback" : undefined}
        disablePictureInPicture={expandable || undefined}
        src={src}
      ></video>
    );
  }

  return (
    <>
      <RenderedMarkdown body={caption} />
      {expandable ? (
        <div
          className="gui-media-preview-wrap"
          style={{ position: "relative", maxWidth: 450 }}
        >
          {media}
          <button
            aria-label="Expand video"
            title="Expand video"
            className="gui-media-expand-btn"
            onClick={() => setDialogOpen(true)}
            style={expandButtonStyle}
          >
            <i
              className="fa-solid fa-sm fa-up-right-and-down-left-from-center"
              aria-hidden="true"
            ></i>
          </button>
        </div>
      ) : (
        media
      )}
      {expandable && dialogOpen && (
        <MediaPreviewDialog onClose={() => setDialogOpen(false)} alt={caption}>
          <video
            src={src}
            controls
            autoPlay
            playsInline
            style={mediaDialogStyle}
          ></video>
        </MediaPreviewDialog>
      )}
    </>
  );
}

const mediaDialogStyle: React.CSSProperties = {
  display: "block",
  maxWidth: "90vw",
  maxHeight: "90vh",
  borderRadius: 8,
  objectFit: "contain",
};

const expandButtonStyle: React.CSSProperties = {
  position: "absolute",
  // Top corner, clear of the video's own control bar (bottom) so the two
  // don't visually compete.
  top: 8,
  right: 8,
  zIndex: 2,
  borderRadius: "50%",
  width: 28,
  height: 28,
  // Semi-transparent dark, like a player control overlay, so it reads
  // clearly regardless of the video's own colors.
  background: "rgba(0,0,0,0.55)",
  color: "#fff",
  border: "none",
  boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
};

function MediaPreviewDialog({
  onClose,
  alt,
  children,
}: {
  onClose: () => void;
  alt?: string;
  children: React.ReactNode;
}) {
  // Prevent background scroll while open, and close on Escape.
  useEffect(() => {
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = original;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  return ReactDOM.createPortal(
    <div
      role="presentation"
      aria-label={alt || "Media preview"}
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        width: "100vw",
        height: "100vh",
        zIndex: 999999,
        background: "rgba(255,255,255,0.85)",
        backdropFilter: "blur(16px) saturate(180%)",
        WebkitBackdropFilter: "blur(16px) saturate(180%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        boxSizing: "border-box",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="gui-media-preview-wrap"
        onClick={(e) => e.stopPropagation()}
        style={{ position: "relative", maxWidth: "90vw", maxHeight: "90vh" }}
      >
        <button
          aria-label="Close preview"
          title="Close preview"
          className="gui-media-expand-btn"
          onClick={onClose}
          style={expandButtonStyle}
        >
          <i className="fa fa-times" aria-hidden="true"></i>
        </button>
        {children}
      </div>
    </div>,
    document.body,
  );
}

/**
 * Validates an image URL by loading it through a fresh `Image` element so the
 * `load`/`error` handlers are guaranteed to be attached before the request
 * starts. This sidesteps the React SSR hydration race documented at
 * https://github.com/facebook/react/issues/15446 (where `onError` on a
 * server-rendered `<img>` can fire before React hydrates and is dropped).
 *
 * Adapted from `react-component/image` (used by ant-design):
 * https://github.com/react-component/image/blob/master/src/util.ts
 */
function useImageValid(src?: string): [boolean, () => void] {
  const [isValid, setIsValid] = useState(true);

  useEffect(() => {
    if (!src) return;
    // Optimistically assume the new src is valid so we don't waste bandwidth
    // fetching the full asset while parallel validation runs.
    setIsValid(true);

    let ignore = false;
    let img = new Image();
    img.onload = () => {
      if (!ignore) setIsValid(true);
    };
    img.onerror = () => {
      if (!ignore) setIsValid(false);
    };
    img.src = src;

    return () => {
      ignore = true;
    };
  }, [src]);

  return [isValid, () => setIsValid(false)];
}
