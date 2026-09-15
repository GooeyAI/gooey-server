import React, { useEffect, useRef, useState } from "react";
import ReactDOM, { flushSync } from "react-dom";
import { RenderedMarkdown } from "~/renderedMarkdown";
import { Link } from "@remix-run/react";
import { urlToFilename } from "~/urlUtils";

// Not yet in this project's DOM lib (React 17 / an older TS target) - typed
// just enough to call it.
declare global {
  interface Document {
    startViewTransition?(update: () => void): { finished: Promise<void> };
  }
}

// Morphs the media card's position/size/radius between the thumbnail and the
// dialog (matched by view-transition-name on each side) - browser support
// only (Chromium, Safari 18+), no dependency. Where it's unsupported, or the
// user has asked for reduced motion, this just runs the update plainly, same
// as the dialog opening/closing today.
function withViewTransition(update: () => void) {
  const start = typeof document !== "undefined" && document.startViewTransition;
  const prefersReducedMotion =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!start || prefersReducedMotion) {
    update();
    return;
  }
  // .call, not a bare start(...) - it's unbound from `document` once
  // destructured into this local.
  start.call(document, () => flushSync(update));
}

// React 17 has no useId - view-transition-name just needs *some* stable,
// unique-per-instance identifier, and src (the media URL) already is one
// without adding a hook. Sanitized into a valid CSS custom-ident.
function mediaTransitionNameFor(src: string) {
  return "gooey-media-" + src.replace(/[^a-zA-Z0-9_-]/g, "");
}

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
  const mediaTransitionName = mediaTransitionNameFor(src);

  let currentSrc;
  if (previewImg && previewIsValid) {
    currentSrc = previewImg;
  } else {
    currentSrc = src;
  }

  const clickable =
    enablePreviewDialog && !href && !currentSrc.startsWith("data:");

  const openDialog = () => withViewTransition(() => setDialogOpen(true));

  const img = (
    <img
      className={"gui-img" + (clickable ? " gui-img-clickable" : "")}
      alt={caption}
      src={currentSrc}
      onError={onError}
      {...props}
      onClick={clickable ? openDialog : props.onClick}
    />
  );

  let child = (
    <>
      <RenderedMarkdown body={caption} />
      {clickable ? (
        <div
          className="gui-media-preview-wrap"
          style={{
            position: "relative",
            maxWidth: 450,
            viewTransitionName: dialogOpen ? undefined : mediaTransitionName,
          }}
        >
          {img}
          {/* Hover/cursor affordances (zoom-in cursor) aren't visible on
              touch devices, so show an explicit expand icon too - CSS fades
              it in on hover for mouse users, but keeps it always-on for
              touch (see .gui-media-expand-btn in app.css). */}
          <button
            type="button"
            aria-label="Expand image"
            title="Expand image"
            className="gui-media-expand-btn"
            onClick={openDialog}
            style={mediaExpandButtonStyle}
          >
            <i
              className="fa-solid fa-sm fa-up-right-and-down-left-from-center"
              style={expandIconStyle}
              aria-hidden="true"
            ></i>
          </button>
        </div>
      ) : (
        img
      )}
      {clickable && dialogOpen && (
        <MediaPreviewDialog
          onClose={() => withViewTransition(() => setDialogOpen(false))}
          alt={caption}
          src={src}
          mediaTransitionName={mediaTransitionName}
        >
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
  const mediaTransitionName = mediaTransitionNameFor(src);

  const expandable = enablePreviewDialog && !href;
  const showingVideoElement = !(previewImg && previewIsValid);
  // The play/pause/mute overlay only makes sense against a real <video> -
  // the previewImg fallback is a static <img>, nothing to play or mute.
  const isPlayable = expandable && showingVideoElement;

  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const wasPlayingBeforeDialog = useRef(false);

  const [isMuted, setIsMuted] = useState(true);
  const [userPaused, setUserPaused] = useState(false);
  const [isIntersecting, setIsIntersecting] = useState(true);
  const [controlsVisible, setControlsVisible] = useState(false);

  const shouldPlay = isPlayable && !userPaused && isIntersecting;

  // Drive actual playback from our own state - not just the autoPlay
  // attribute - so pause/scroll/the dialog can all affect it afterwards.
  // src is included even though it's not read directly: a recipe rerun can
  // swap the video URL on this same component instance without shouldPlay
  // itself changing, and the new source's autoPlay attribute would
  // otherwise start it playing regardless of our (possibly still paused)
  // state until something else happened to flip a dependency.
  useEffect(() => {
    const el = videoRef.current;
    if (!el || !isPlayable) return;
    if (shouldPlay) el.play().catch(() => {});
    else el.pause();
  }, [shouldPlay, isPlayable, src]);

  // React's `muted` JSX prop only sets the *initial* value - toggling it via
  // re-render doesn't reliably update the live DOM property, so drive it
  // imperatively too.
  useEffect(() => {
    const el = videoRef.current;
    if (el) el.muted = isMuted;
  }, [isMuted]);

  // Pause (without counting it as a user pause) once scrolled out of view,
  // and resume automatically once back in view - unless the user explicitly
  // paused it themselves in the meantime, which should stick either way.
  useEffect(() => {
    if (!isPlayable || typeof IntersectionObserver === "undefined") return;
    const el = wrapperRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setIsIntersecting(entry.isIntersecting),
      { threshold: 0 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [isPlayable]);

  const showControls = () => {
    setControlsVisible(true);
    clearTimeout(hideTimeoutRef.current);
    hideTimeoutRef.current = setTimeout(() => setControlsVisible(false), 1500);
  };
  const hideControlsNow = () => {
    clearTimeout(hideTimeoutRef.current);
    setControlsVisible(false);
  };
  useEffect(() => () => clearTimeout(hideTimeoutRef.current), []);

  let media;
  if (!showingVideoElement) {
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
        ref={videoRef}
        className="gui-video"
        {...props}
        // The dialog already offers a full native player, and native
        // controls on the inline thumbnail is what caused the AirPlay-icon/
        // corner-bleeding bugs (see gooey-web-widget's MediaPreview, which
        // never shows controls inline either) - so drop them here in favor
        // of our own play/pause + mute + expand overlay below. Still block
        // PiP/AirPlay from the right-click context menu, since browsers can
        // offer those even without visible controls.
        controls={expandable ? false : props.controls}
        autoPlay={expandable ? true : props.autoPlay}
        muted={expandable ? true : props.muted}
        loop={expandable ? true : props.loop}
        playsInline={expandable ? true : props.playsInline}
        disablePictureInPicture={expandable || undefined}
        disableRemotePlayback={expandable || undefined}
        src={src}
      ></video>
    );
  }

  return (
    <>
      <RenderedMarkdown body={caption} />
      {expandable ? (
        <div
          ref={wrapperRef}
          className={
            "gui-media-preview-wrap" +
            (controlsVisible ? " gui-video-controls-visible" : "")
          }
          style={{
            position: "relative",
            maxWidth: 450,
            viewTransitionName: dialogOpen ? undefined : mediaTransitionName,
          }}
          onMouseMove={showControls}
          onMouseLeave={hideControlsNow}
          onClick={() => {
            // A tap on the video itself (anything but a button, which stops
            // propagation below) only reveals the overlay - it shouldn't
            // also toggle mute/playback, or the same tap meant to reveal
            // the buttons could catch someone off guard with sudden audio.
            if (!controlsVisible) showControls();
          }}
        >
          {media}
          <button
            type="button"
            aria-label="Expand video"
            title="Expand video"
            // isPlayable: governed only by the timer-driven group below,
            // same as mute/play-pause - .gui-media-expand-btn's plain
            // :hover rule fires independent of that timer (it doesn't care
            // whether the mouse has actually moved recently), so carrying
            // both classes left this the only button still visible once the
            // others faded out from under a motionless cursor.
            className={
              isPlayable ? "gui-video-overlay-btn" : "gui-media-expand-btn"
            }
            onClick={(e) => {
              e.stopPropagation();
              wasPlayingBeforeDialog.current = !!shouldPlay;
              withViewTransition(() => {
                setUserPaused(true);
                setDialogOpen(true);
              });
            }}
            style={mediaExpandButtonStyle}
          >
            <i
              className="fa-solid fa-sm fa-up-right-and-down-left-from-center"
              style={expandIconStyle}
              aria-hidden="true"
            ></i>
          </button>
          {isPlayable && (
            <>
              <button
                type="button"
                aria-label={isMuted ? "Unmute" : "Mute"}
                title={isMuted ? "Unmute" : "Mute"}
                className="gui-video-overlay-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  showControls();
                  setIsMuted((m) => !m);
                }}
                style={videoMuteButtonStyle}
              >
                <i
                  className={
                    "fa-solid " +
                    (isMuted ? "fa-volume-xmark" : "fa-volume-high")
                  }
                  aria-hidden="true"
                ></i>
              </button>
              <button
                type="button"
                aria-label={shouldPlay ? "Pause" : "Play"}
                title={shouldPlay ? "Pause" : "Play"}
                className="gui-video-overlay-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  showControls();
                  setUserPaused((p) => !p);
                }}
                style={videoPlayPauseButtonStyle}
              >
                <i
                  className={"fa-solid " + (shouldPlay ? "fa-pause" : "fa-play")}
                  style={shouldPlay ? undefined : { marginLeft: 2 }}
                  aria-hidden="true"
                ></i>
              </button>
            </>
          )}
        </div>
      ) : (
        media
      )}
      {expandable && dialogOpen && (
        <MediaPreviewDialog
          onClose={() => {
            withViewTransition(() => {
              setDialogOpen(false);
              // Only resume if it was actually playing before Expand was
              // clicked - if the user had already paused it themselves,
              // closing the dialog should respect that instead of
              // overriding it.
              if (wasPlayingBeforeDialog.current) setUserPaused(false);
            });
          }}
          mediaTransitionName={mediaTransitionName}
          alt={caption}
          src={src}
        >
          <video
            src={src}
            controls
            autoPlay
            playsInline
            disableRemotePlayback
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

const circleButtonStyle: React.CSSProperties = {
  borderRadius: "50%",
  width: 28,
  height: 28,
  // Semi-transparent dark, like a player control overlay, so it reads
  // clearly regardless of the media's own colors.
  background: "rgba(0,0,0,0.55)",
  color: "#fff",
  border: "none",
  boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  cursor: "pointer",
  flexShrink: 0,
};

// FontAwesome's up-right-and-down-left-from-center points along the
// opposite diagonal from iOS's native expand/fullscreen glyph (up-left +
// down-right) - there's no separate icon asset for that diagonal, so rotate
// this one 90deg to match instead.
const expandIconStyle: React.CSSProperties = {
  // A horizontal mirror (rather than a 90deg rotation) turns the up-right/
  // down-left diagonal into up-left/down-right, matching iOS's native
  // expand glyph - and unlike rotate(), scaleX doesn't change the glyph's
  // own box shape, so it can't throw off the centering the parent button's
  // flex layout already provides.
  transform: "scaleX(-1)",
};

// Shared by GooeyImg and GooeyVideo, so the expand affordance sits in the
// same corner on both. Top-left specifically because GooeyVideo's overlay
// mirrors where native video controls conventionally put things, and
// top-right is where Safari's own AirPlay icon claims - see
// disableRemotePlayback above; better to own that corner with a mute
// control of ours than contest it again.
const mediaExpandButtonStyle: React.CSSProperties = {
  ...circleButtonStyle,
  position: "absolute",
  top: 8,
  left: 8,
  zIndex: 2,
};

const videoMuteButtonStyle: React.CSSProperties = {
  ...circleButtonStyle,
  position: "absolute",
  top: 8,
  right: 8,
  zIndex: 2,
};

const videoPlayPauseButtonStyle: React.CSSProperties = {
  ...circleButtonStyle,
  position: "absolute",
  top: "50%",
  left: "50%",
  transform: "translate(-50%, -50%)",
  width: 44,
  height: 44,
  fontSize: 16,
  zIndex: 2,
};

const mediaDialogSurfaceStyle: React.CSSProperties = {
  position: "relative",
  maxWidth: "90vw",
  maxHeight: "90vh",
  // A neutral dark surface (matching gooey-web-widget's MediaPreview) so
  // photos/videos of any color sit against a consistent backdrop, distinct
  // from the page's own light, blurred one behind it.
  background: "#0b1021",
  borderRadius: 12,
  boxShadow: "0 20px 60px rgba(0,0,0,0.35)",
};

// position:fixed (not absolute) and anchored to the viewport corner, not
// nested-but-relative-to the surface panel above - otherwise this floats on
// top of the media itself and competes with the native control bar in
// there, which is what it was doing before.
const dialogActionBarStyle: React.CSSProperties = {
  position: "fixed",
  top: 16,
  right: 16,
  zIndex: 1000000,
  display: "flex",
  alignItems: "center",
  gap: 8,
};

const actionPillButtonStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  height: 28,
  padding: "0 12px",
  borderRadius: 14,
  background: "rgba(0,0,0,0.55)",
  color: "#fff",
  border: "none",
  boxShadow: "0 2px 8px rgba(0,0,0,0.25)",
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 600,
  whiteSpace: "nowrap",
};

function MediaPreviewDialog({
  onClose,
  alt,
  src,
  mediaTransitionName,
  children,
}: {
  onClose: () => void;
  alt?: string;
  src: string;
  mediaTransitionName: string;
  children: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  // The caller passes an inline onClose, recreated on every render (and
  // GooeyVideo's own state - mute, pause, scroll visibility - re-renders
  // often); reading it via a ref instead of the closure lets the focus
  // effect below depend on nothing but mount/unmount, rather than tearing
  // down and re-running (bouncing focus out and back) on every one of those.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [linkCopied, setLinkCopied] = useState(false);

  const handleDownload = async () => {
    try {
      const response = await fetch(src);
      // fetch() only rejects on a network failure - an HTTP error still
      // resolves normally, so without this a 404/403 page gets downloaded
      // as if it were the actual media file.
      if (!response.ok) {
        throw new Error(`Download failed with status ${response.status}`);
      }
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = urlToFilename(src);
      document.body.appendChild(link);
      link.click();
      // Revoking immediately can race Safari/iOS's queued download
      // navigation, invalidating the URL before it's actually read - match
      // the delay downloadButton.tsx already uses for the same reason.
      setTimeout(() => {
        link.remove();
        URL.revokeObjectURL(blobUrl);
      }, 250);
    } catch {
      window.open(src, "_blank", "noopener,noreferrer");
    }
  };

  const handleCopyLink = () => {
    if (!navigator.clipboard) {
      window.prompt("Copy this link", src);
      return;
    }
    navigator.clipboard
      .writeText(src)
      .then(() => {
        setLinkCopied(true);
        setTimeout(() => setLinkCopied(false), 1500);
      })
      .catch(() => window.prompt("Copy this link", src));
  };

  // Prevent background scroll while open, close on Escape, and manage focus:
  // move focus into the dialog on open, trap Tab within it, and restore focus
  // to the launching element on close.
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();

    const getFocusable = () =>
      Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, video, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute("disabled"));

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = getFocusable();
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first || document.activeElement === dialogRef.current) {
          e.preventDefault();
          last.focus();
        }
      } else if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = original;
      window.removeEventListener("keydown", handleKeyDown);
      previouslyFocused.current?.focus();
    };
  }, []);

  return ReactDOM.createPortal(
    <div
      role="presentation"
      onClick={onClose}
      style={{
        position: "fixed",
        // No explicit width/height here on purpose - competing vw/vh
        // lengths alongside inset:0 resolve against the safe-area-excluding
        // layout viewport on iOS, which is what left a gap at the notch/
        // Dynamic Island. Sized by inset:0 alone (matching
        // gooey-web-widget's MediaPreview, confirmed not to have this gap),
        // it resolves against the fixed-positioning containing block
        // instead, which does extend edge-to-edge.
        inset: 0,
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
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={alt || "Media preview"}
        tabIndex={-1}
        className="gui-media-preview-wrap"
        onClick={(e) => e.stopPropagation()}
        style={{ ...mediaDialogSurfaceStyle, viewTransitionName: mediaTransitionName }}
      >
        <div style={dialogActionBarStyle}>
          {/* Labeled, unlike Close below - the download/copy icons alone
              aren't obvious to everyone, and there's room for text here
              since this bar floats over the backdrop rather than the media
              itself. */}
          <button
            type="button"
            onClick={handleDownload}
            style={actionPillButtonStyle}
          >
            <i className="fa-solid fa-download" aria-hidden="true"></i>
            <span>Download</span>
          </button>
          <button
            type="button"
            onClick={handleCopyLink}
            style={actionPillButtonStyle}
          >
            <i
              className={`fa-solid ${linkCopied ? "fa-check" : "fa-link"}`}
              aria-hidden="true"
            ></i>
            <span>{linkCopied ? "Copied" : "Copy link"}</span>
          </button>
          <button
            type="button"
            aria-label="Close preview"
            title="Close preview"
            onClick={onClose}
            style={circleButtonStyle}
          >
            <i className="fa fa-times" aria-hidden="true"></i>
          </button>
        </div>
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
