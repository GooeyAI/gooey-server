import type { CustomComponentProps } from "~/components";
import { RenderedChildren } from "~/renderer";
import { type CSSProperties, useEffect, useRef, useState } from "react";
import SidebarResizer from "./SidebarResizer";

export function Sidebar({
  name,
  children,
  onChange,
  state,
  defaultOpen,
  disabled,
  enableResize = true,
  clientOnly = false,
  storageKey = "",
}: CustomComponentProps & {
  name: string;
  defaultOpen: boolean;
  disabled: boolean;
  enableResize?: boolean;
  clientOnly?: boolean;
  storageKey?: string;
}) {
  const [isOpen, setOpen] = useState(defaultOpen);
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(null);
  const [storageReady, setStorageReady] = useState(!clientOnly);
  const sidebarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      sidebarRef.current?.removeAttribute("inert");
      return;
    }
    sidebarRef.current?.setAttribute("inert", "");
  }, [isOpen]);

  // An explicit `:open` / `:close` command - the rail opening a Builder chat, the panel's own
  // close button - outranks the persisted default. Without this the storage restore below
  // runs on mount and puts the panel straight back to whatever the user last left it at,
  // silently dropping the command.
  const commandedRef = useRef(false);

  useEffect(() => {
    function handleOpen() {
      commandedRef.current = true;
      setOpen(true);
    }
    function handleClose() {
      commandedRef.current = true;
      setOpen(false);
    }
    window.addEventListener(name + ":open", handleOpen);
    window.addEventListener(name + ":close", handleClose);
    return () => {
      window.removeEventListener(name + ":open", handleOpen);
      window.removeEventListener(name + ":close", handleClose);
    };
  }, [name]);

  useEffect(() => {
    for (const openBtn of document.getElementsByClassName(
      name + "-button"
    ) as HTMLCollectionOf<HTMLButtonElement>) {
      openBtn.style.display = isOpen ? "none" : "inline-flex";
    }
  }, [isOpen, name]);

  useEffect(() => {
    if (!clientOnly) {
      return;
    }
    if (!storageKey) {
      setStorageReady(true);
      return;
    }
    try {
      const stored = window.sessionStorage.getItem(storageKey);
      // `!commandedRef.current` so a restore cannot undo an open/close that was asked for
      // explicitly, whichever of the two effects happens to run first
      if (stored !== null && !commandedRef.current) {
        setOpen(stored === "true");
      }
    } catch {
      // Storage can be unavailable; the server-provided default remains usable.
    }
    setStorageReady(true);
  }, [clientOnly, storageKey]);

  useEffect(() => {
    if (clientOnly) {
      if (!storageReady) {
        return;
      }
      if (storageKey) {
        try {
          window.sessionStorage.setItem(storageKey, String(isOpen));
        } catch {
          // The pane still works without persistence.
        }
      }
      return;
    }
    if (state[name] != isOpen) {
      state[name] = isOpen;
      if (isDesktop()) {
        state[name + ":default-open"] = isOpen;
      } else {
        state[name + ":default-open"] = false;
      }
      onChange();
    }
  }, [clientOnly, isOpen, name, onChange, state, storageKey, storageReady]);

  let [sidebarDiv, pageDiv] = children;

  if (disabled) {
    return (
      <RenderedChildren
        children={pageDiv.children}
        onChange={onChange}
        state={state}
      />
    );
  }

  let sidebarClassName;
  if (isOpen) {
    sidebarClassName = "gooey-sidebar-open";
  } else {
    sidebarClassName = "gooey-sidebar-closed";
  }

  let pageClassName;
  if (isOpen) {
    pageClassName = "mx-2 w-100";
  } else {
    pageClassName = "w-100";
  }

  // The width the panel settles at, published as a custom property so its content can be
  // sized against that instead of against the panel while the panel is mid-transition. The
  // panel animates min/max/width - layout properties - so anything at `width: 100%` inside it
  // re-lays-out on every frame, which is what makes the chat text reflow as it slides. Held
  // here rather than in CSS because a resized panel's width only exists in JS.
  const settledWidth = sidebarWidth
    ? `${sidebarWidth}px`
    : "var(--sidebar_open_width)";

  const sidebarContainerStyles = {
    ...(isOpen && sidebarWidth
      ? { width: sidebarWidth, minWidth: sidebarWidth, maxWidth: sidebarWidth }
      : {}),
    "--sidebar-settled-width": settledWidth,
  } as CSSProperties;

  const sidebarContainerClassName = `flex-column flex-grow-1 gooey-sidebar ${sidebarClassName} ${
    enableResize ? "gooey-sidebar-resizable" : "gooey-sidebar-bordered"
  }`;

  return (
    <div
      className={`d-flex w-100 h-100 position-relative ${
        isOpen ? "gap-2" : "gap-0"
      }`}
    >
      <div
        ref={sidebarRef}
        className={sidebarContainerClassName}
        style={sidebarContainerStyles}
      >
        <RenderedChildren
          children={sidebarDiv.children}
          onChange={onChange}
          state={state}
        />
        {!!enableResize && !!isOpen && (
          <SidebarResizer
            minWidth={340}
            maxWidth={800}
            width={sidebarWidth}
            onWidthChange={setSidebarWidth}
          />
        )}
      </div>
      <div className={`d-flex flex-grow-1 mw-100`}>
        <div className={pageClassName}>
          <RenderedChildren
            children={pageDiv.children}
            onChange={onChange}
            state={state}
          />
        </div>
      </div>
    </div>
  );
}

function isDesktop() {
  if (typeof window === "undefined") return false;
  const breakpoint =
    parseInt(
      getComputedStyle(document.documentElement).getPropertyValue(
        "--sidebar_desktop_breakpoint"
      ),
      10
    ) || 1140;
  return window.innerWidth >= breakpoint;
}
