import React, { useEffect, useRef, useState } from "react";
import ReactDOM, { flushSync } from "react-dom";
import clsx from "clsx";
import { RenderedMarkdown } from "~/renderedMarkdown";
import { Link } from "@remix-run/react";
import { urlToFilename } from "~/urlUtils";
import "./MediaTags.css";

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
  // gui.image emits data: URIs for numpy-array inputs (tens of KB, bounded
  // by a 128px resize) - src is only sanitized into a name when actually
  // needed, gated on `clickable`, so a non-clickable data: URI image
  // doesn't run a regex over that whole string just to throw it away.
  const mediaTransitionName = useMediaTransitionName(src, clickable);

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
          className="gui-media-preview-wrap position-relative"
          style={{ viewTransitionName: dialogOpen ? undefined : mediaTransitionName }}
        >
          {img}
          {/* Hover/cursor affordances (zoom-in cursor) aren't visible on
              touch devices, so show an explicit expand icon too - CSS fades
              it in on hover for mouse users, but keeps it always-on for
              touch (see .gui-media-expand-btn in MediaTags.css). */}
          <button
            type="button"
            aria-label="Expand image"
            title="Expand image"
            className="gui-media-circle-btn gui-media-expand-position gui-media-expand-btn"
            onClick={openDialog}
          >
            <i
              className="fa-solid fa-sm fa-up-right-and-down-left-from-center gui-media-expand-icon"
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
          <img src={src} alt={caption} className="gui-media-dialog-content" />
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
  const mediaTransitionName = useMediaTransitionName(src, expandable);
  const showingVideoElement = !(previewImg && previewIsValid);
  // The play/pause/mute overlay only makes sense against a real <video> -
  // the previewImg fallback is a static <img>, nothing to play or mute.
  const isPlayable = expandable && showingVideoElement;

  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const lastShowControlsAtRef = useRef(0);
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
    // onMouseMove fires ~60 times/sec while the cursor is actively moving -
    // resetting the hide-timer on every single one is wasted timer churn
    // that multiplies across a page with several videos (e.g.
    // CompareText2Img renders one per model). Once already visible, only
    // actually reset it at most every 200ms; the very first call (from
    // hidden) still runs immediately so revealing still feels instant.
    const now = Date.now();
    if (controlsVisible && now - lastShowControlsAtRef.current < 200) return;
    lastShowControlsAtRef.current = now;
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
          className={clsx(
            "gui-media-preview-wrap",
            "position-relative",
            controlsVisible && "gui-video-controls-visible",
          )}
          style={{ viewTransitionName: dialogOpen ? undefined : mediaTransitionName }}
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
            className={clsx(
              "gui-media-circle-btn",
              "gui-media-expand-position",
              isPlayable ? "gui-video-overlay-btn" : "gui-media-expand-btn",
            )}
            onClick={(e) => {
              e.stopPropagation();
              wasPlayingBeforeDialog.current = !!shouldPlay;
              withViewTransition(() => {
                setUserPaused(true);
                setDialogOpen(true);
              });
            }}
          >
            <i
              className="fa-solid fa-sm fa-up-right-and-down-left-from-center gui-media-expand-icon"
              aria-hidden="true"
            ></i>
          </button>
          {isPlayable && (
            <>
              <button
                type="button"
                aria-label={isMuted ? "Unmute" : "Mute"}
                title={isMuted ? "Unmute" : "Mute"}
                className="gui-media-circle-btn gui-video-mute-btn gui-video-overlay-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  showControls();
                  setIsMuted((m) => !m);
                }}
              >
                <i
                  className={clsx(
                    "fa-solid",
                    isMuted ? "fa-volume-xmark" : "fa-volume-high",
                  )}
                  aria-hidden="true"
                ></i>
              </button>
              <button
                type="button"
                aria-label={shouldPlay ? "Pause" : "Play"}
                title={shouldPlay ? "Pause" : "Play"}
                className="gui-media-circle-btn gui-video-playpause-btn gui-video-overlay-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  showControls();
                  setUserPaused((p) => !p);
                }}
              >
                <i
                  className={clsx(
                    "fa-solid",
                    shouldPlay ? "fa-pause" : "fa-play",
                    !shouldPlay && "gui-media-play-icon-offset",
                  )}
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
            className="gui-media-dialog-content"
          ></video>
        </MediaPreviewDialog>
      )}
    </>
  );
}

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
    // Safari/iOS only allow window.open() within the synchronous tick of a
    // user gesture ("transient activation"), which the fetch below can
    // easily outlive - so the fallback window.open() in the catch block
    // could get silently popup-blocked right when it's needed. Open a blank
    // placeholder synchronously now instead, then either close it (success)
    // or navigate it to src (fallback). Can't pass noopener/noreferrer here
    // since that severs the reference needed to do either, so the opener
    // link is cut manually instead, right before navigating it below.
    const fallbackWindow = window.open();
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
      fallbackWindow?.close();
    } catch {
      if (fallbackWindow) {
        // Without noopener, this window still holds a `window.opener` back
        // to us - src isn't restricted to our own origin at the type level,
        // so clear that link before navigating rather than trust it'll
        // always be one of our own trusted media URLs.
        fallbackWindow.opener = null;
        fallbackWindow.location.href = src;
      } else {
        window.open(src, "_blank", "noopener,noreferrer");
      }
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
      className="gui-media-dialog-backdrop"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={alt || "Media preview"}
        tabIndex={-1}
        className="gui-media-preview-wrap gui-media-dialog-surface"
        onClick={(e) => e.stopPropagation()}
        style={{ viewTransitionName: mediaTransitionName }}
      >
        <div className="gui-media-dialog-action-bar">
          {/* Labeled, unlike Close below - the download/copy icons alone
              aren't obvious to everyone, and there's room for text here
              since this bar floats over the backdrop rather than the media
              itself. */}
          <button
            type="button"
            onClick={handleDownload}
            className="gui-media-action-pill"
          >
            <i className="fa-solid fa-download" aria-hidden="true"></i>
            <span>Download</span>
          </button>
          <button
            type="button"
            onClick={handleCopyLink}
            className="gui-media-action-pill"
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
            className="gui-media-action-icon"
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

// A src-based name alone collides whenever two expandable instances share a
// source (e.g. Img2Img renders one expandable image per output in a loop) -
// the browser sees a duplicate view-transition-name in the "before"
// snapshot and aborts the transition for both. React 17 has no useId, so
// the per-instance part comes from a plain module-level counter instead,
// assigned once per instance via a lazily-initialized ref. Render order is
// deterministic between the server and hydration, so this stays consistent
// across both rather than needing anything client-only like Math.random().
let mediaTransitionInstanceCounter = 0;

function useMediaTransitionName(src: string, active: boolean | undefined) {
  const instanceId = useRef<number>();
  if (instanceId.current === undefined) {
    instanceId.current = mediaTransitionInstanceCounter++;
  }
  if (!active) return "";
  return (
    "gooey-media-" +
    src.replace(/[^a-zA-Z0-9_-]/g, "") +
    "-" +
    instanceId.current
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
