import type { TreeNode } from "~/renderer";
import { RenderedChildren } from "~/renderer";
import type { OnChange } from "~/app";
import { useEffect, useState } from "react";
import SidebarResizer from "./SidebarResizer";

export default function GooeySidebar({
  name,
  children,
  onChange,
  state,
  defaultOpen,
  disabled,
  enableResize = true,
}: {
  name: string;
  children: Array<TreeNode>;
  onChange: OnChange;
  state: Record<string, any>;
  defaultOpen: boolean;
  disabled: boolean;
  enableResize?: boolean;
}) {
  const [isOpen, setOpen] = useState(defaultOpen);
  const [sidebarWidth, setSidebarWidth] = useState<number | null>(null);

  useEffect(() => {
    function handleOpen() {
      setOpen(true);
      for (const openBtn of document.getElementsByClassName(
        name + "-button"
      ) as HTMLCollectionOf<HTMLButtonElement>) {
        openBtn.style.display = "none";
      }
    }
    function handleClose() {
      setOpen(false);
      for (const openBtn of document.getElementsByClassName(
        name + "-button"
      ) as HTMLCollectionOf<HTMLButtonElement>) {
        openBtn.style.display = "inline-block";
      }
    }
    window.addEventListener(name + ":open", handleOpen);
    window.addEventListener(name + ":close", handleClose);
    return () => {
      window.removeEventListener(name + ":open", handleOpen);
      window.removeEventListener(name + ":close", handleClose);
    };
  }, [name]);

  useEffect(() => {
    if (state[name] != isOpen) {
      state[name] = isOpen;
      if (isDesktop()) {
        state[name + ":default-open"] = isOpen;
      } else {
        state[name + ":default-open"] = false;
      }
      onChange();
    }
  }, [isOpen, name, state]);

  let [sidebarDiv, pageDiv] = children;

  if (disabled) {
    return (
      <div className="container-xl">
        <RenderedChildren
          children={pageDiv.children}
          onChange={onChange}
          state={state}
        />
      </div>
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
    pageClassName = "container-xxl";
  }

  const sidebarContainerStyles = sidebarWidth
    ? { width: sidebarWidth, minWidth: sidebarWidth, maxWidth: sidebarWidth }
    : undefined;

  const sidebarContainerClassName = `flex-column flex-grow-1 gooey-sidebar ${sidebarClassName} ${
    enableResize ? "gooey-sidebar-resizable" : "gooey-sidebar-bordered"
  }`;

  return (
    <div className="d-flex w-100 h-100 position-relative gap-2">
      <div className={sidebarContainerClassName} style={sidebarContainerStyles}>
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
