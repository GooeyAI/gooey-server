import type { CustomComponentProps } from "~/components";
import { RenderedChildren } from "~/renderer";
import { type CSSProperties, useEffect, useRef, useState } from "react";
import { useAppShellPanel } from "~/appShellContext";
import type { SidebarProps } from "@gooey-types/sidebar_props";
import SidebarResizer from "./SidebarResizer";

export function Sidebar({
  name,
  children,
  onChange,
  state,
  default_open,
  disabled,
  enable_resize,
  client_only,
  storage_key,
}: CustomComponentProps & SidebarProps) {
  const [legacyOpen, setLegacyOpen] = useState(default_open);
  const managedPanel = useAppShellPanel(
    client_only ? name : null,
    default_open,
    client_only ? storage_key : null
  );
  const isOpen = client_only ? managedPanel.open : legacyOpen;
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      sidebarRef.current?.removeAttribute("inert");
      return;
    }
    sidebarRef.current?.setAttribute("inert", "");
  }, [isOpen]);

  useEffect(() => {
    if (client_only) {
      return;
    }
    function handleOpen() {
      setLegacyOpen(true);
    }
    function handleClose() {
      setLegacyOpen(false);
    }
    window.addEventListener(name + ":open", handleOpen);
    window.addEventListener(name + ":close", handleClose);
    return () => {
      window.removeEventListener(name + ":open", handleOpen);
      window.removeEventListener(name + ":close", handleClose);
    };
  }, [client_only, name]);

  useEffect(() => {
    for (const openBtn of document.getElementsByClassName(
      name + "-button"
    ) as HTMLCollectionOf<HTMLButtonElement>) {
      openBtn.style.display = isOpen ? "none" : "inline-flex";
    }
  }, [isOpen, name]);

  useEffect(() => {
    if (client_only || disabled) {
      return;
    }
    window.dispatchEvent(
      new CustomEvent(name + ":changed", { detail: { open: isOpen } })
    );
  }, [client_only, disabled, isOpen, name]);

  useEffect(() => {
    if (client_only) {
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
  }, [client_only, isOpen, name, onChange, state]);

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

  // The width the panel settles at, so content can size against that rather than against a
  // panel mid-transition. In JS because a resized panel's width exists nowhere else.
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
    enable_resize ? "gooey-sidebar-resizable" : "gooey-sidebar-bordered"
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
        {!!enable_resize && !!isOpen && (
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
