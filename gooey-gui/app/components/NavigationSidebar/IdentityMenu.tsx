import Tippy from "@tippyjs/react";
import { useState } from "react";
import type {
  MenuLinkData,
  NavUserData,
  WorkspaceData,
} from "@gooey-types/navigation_sidebar_props";

function Avatar({ user, size = 28 }: { user: NavUserData; size?: number }) {
  if (user.photo_url) {
    return (
      <img
        src={user.photo_url}
        alt=""
        width={size}
        height={size}
        className="rounded-circle flex-shrink-0"
        style={{ objectFit: "cover" }}
      />
    );
  }
  return (
    <span
      className="rounded-circle bg-secondary text-white d-inline-flex align-items-center justify-content-center flex-shrink-0 fw-semibold"
      style={{ width: size, height: size, fontSize: size * 0.42 }}
    >
      {user.initial}
    </span>
  );
}

/** Renders a workspace's `html_icon()` (an <img> or a FontAwesome glyph) inside
 *  a fixed circular slot. */
function WorkspaceIcon({ html, size = 28 }: { html: string; size?: number }) {
  return (
    <span
      className="identity-ws-icon d-inline-flex align-items-center justify-content-center flex-shrink-0"
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

/** One menu row: a FontAwesome icon + label, as a link or a button. */
function MenuItem({
  href,
  icon,
  onClick,
  children,
  trailing,
}: {
  href?: string;
  icon?: string | null;
  onClick?: () => void;
  children: React.ReactNode;
  trailing?: React.ReactNode;
}) {
  const inner = (
    <>
      {icon ? (
        <i
          className={icon}
          style={{ width: 20, textAlign: "center", flexShrink: 0 }}
        />
      ) : (
        <span style={{ width: 20, flexShrink: 0 }} />
      )}
      <span className="flex-grow-1 text-truncate" style={{ minWidth: 0 }}>
        {children}
      </span>
      {trailing}
    </>
  );
  const className =
    "identity-menu-item d-flex align-items-center gap-2 px-3 py-2 text-body text-decoration-none w-100 border-0 text-start";
  if (href) {
    return (
      <a href={href} className={className} onClick={onClick}>
        {inner}
      </a>
    );
  }
  return (
    <button type="button" className={className} onClick={onClick}>
      {inner}
    </button>
  );
}

/** A workspace row: icon + name + subtitle, with a check on the current one. */
function WorkspaceRow({
  ws,
  href,
  onSelect,
}: {
  ws: WorkspaceData;
  href?: string;
  onSelect?: () => void;
}) {
  const inner = (
    <>
      <WorkspaceIcon html={ws.icon_html} />
      <span className="flex-grow-1" style={{ minWidth: 0 }}>
        <span className="d-block text-truncate fw-semibold">{ws.name}</span>
        {ws.subtitle && (
          <span className="d-block text-truncate text-body-secondary small">
            {ws.subtitle}
          </span>
        )}
      </span>
      {ws.is_current && (
        <i className="fa-solid fa-check text-body-secondary flex-shrink-0" />
      )}
    </>
  );
  const className =
    "identity-menu-item d-flex align-items-center gap-2 px-3 py-2 text-body text-decoration-none";
  if (href) {
    return (
      <a href={href} className={className} onClick={onSelect}>
        {inner}
      </a>
    );
  }
  return <div className={className}>{inner}</div>;
}

/** Flyout listing all workspaces + "Add workspace". */
function WorkspaceSwitcher({
  workspaces,
  switchWorkspaceHref,
  addWorkspaceHref,
  onSelect,
}: {
  workspaces: WorkspaceData[];
  switchWorkspaceHref: string;
  addWorkspaceHref: string;
  onSelect?: () => void;
}) {
  return (
    <div className="identity-menu-panel">
      {workspaces.map((ws) => (
        <WorkspaceRow
          key={ws.id}
          ws={ws}
          href={
            ws.is_current
              ? undefined
              : switchWorkspaceHref.replace("{workspace_id}", String(ws.id))
          }
          onSelect={onSelect}
        />
      ))}
      {addWorkspaceHref && (
        <>
          <hr className="my-1" />
          <MenuItem
            href={addWorkspaceHref}
            icon="fa-regular fa-plus"
            onClick={onSelect}
          >
            Add workspace
          </MenuItem>
        </>
      )}
    </div>
  );
}

export function IdentityMenu({
  user,
  currentWorkspace,
  workspaces,
  menuLinks,
  logoutHref,
  switchWorkspaceHref,
  addWorkspaceHref,
  collapsed,
}: {
  user: NavUserData;
  currentWorkspace: WorkspaceData | null;
  workspaces: WorkspaceData[];
  menuLinks: MenuLinkData[];
  logoutHref: string;
  switchWorkspaceHref: string;
  addWorkspaceHref: string;
  collapsed: boolean;
}) {
  const [open, setOpen] = useState(false);
  // The workspace switcher is a controlled submenu so it opens on click (not
  // hover) and can be closed together with the main menu — otherwise it lingers
  // on its own during the main menu's close animation.
  const [wsOpen, setWsOpen] = useState(false);
  const closeMenu = () => {
    setWsOpen(false);
    setOpen(false);
  };

  const menuContent = (
    <div className="identity-menu-panel">
      {currentWorkspace && (
        <>
          <Tippy
            visible={wsOpen}
            onClickOutside={() => setWsOpen(false)}
            interactive
            theme="identity-menu"
            animation="scale"
            duration={120}
            placement="right-start"
            appendTo={() => document.body}
            zIndex={11000}
            arrow={false}
            offset={[0, 8]}
            maxWidth="none"
            // `fixed` strategy anchors the popper to the viewport instead of the
            // document, so it lands next to the button inside the sticky/fixed
            // rail (absolute strategy mispositions it off-screen on tall pages).
            popperOptions={{ strategy: "fixed" }}
            content={
              <WorkspaceSwitcher
                workspaces={workspaces}
                switchWorkspaceHref={switchWorkspaceHref}
                addWorkspaceHref={addWorkspaceHref}
                onSelect={closeMenu}
              />
            }
          >
            <div
              role="button"
              tabIndex={0}
              onClick={() => setWsOpen((v) => !v)}
              className="identity-menu-item identity-ws-current d-flex align-items-center gap-2 px-3 py-2"
            >
              <WorkspaceIcon html={currentWorkspace.icon_html} />
              <span
                className="flex-grow-1 fw-semibold text-truncate"
                style={{ minWidth: 0 }}
              >
                {currentWorkspace.name}
              </span>
              <i className="fa-regular fa-chevron-right text-body-secondary flex-shrink-0" />
            </div>
          </Tippy>
          <hr className="my-1" />
        </>
      )}

      {menuLinks.map((link, i) => (
        <MenuItem key={i} href={link.href} icon={link.icon}>
          {link.label}
        </MenuItem>
      ))}

      {logoutHref && (
        <>
          <hr className="my-1" />
          <MenuItem
            href={logoutHref}
            icon="fa-regular fa-arrow-right-from-bracket"
          >
            Log out
          </MenuItem>
        </>
      )}
    </div>
  );

  return (
    <Tippy
      visible={open}
      onClickOutside={closeMenu}
      interactive
      theme="identity-menu"
      animation="scale"
      duration={120}
      placement="top-start"
      appendTo={() => document.body}
      zIndex={11000}
      arrow={false}
      offset={[0, 8]}
      maxWidth="none"
      // `fixed` strategy anchors the popper to the viewport instead of the
      // document, so it lands above the button inside the sticky/fixed rail
      // (absolute strategy mispositions it off-screen on tall pages).
      popperOptions={{ strategy: "fixed" }}
      content={menuContent}
    >
      <button
        type="button"
        onClick={(e) => {
          // Keep the click here (collapsed rail expands on click otherwise).
          e.stopPropagation();
          setWsOpen(false);
          setOpen((v) => !v);
        }}
        className={[
          "identity-btn d-flex align-items-center w-100 border-0 bg-transparent text-body rounded p-2 bg-hover-light",
          collapsed ? "justify-content-center" : "gap-2",
        ].join(" ")}
        title={collapsed ? currentWorkspace?.name || user.name : undefined}
      >
        {/* Show the current workspace's icon (falls back to the user avatar
            when no workspace is selected) in both collapsed and expanded
            states. */}
        {currentWorkspace ? (
          <WorkspaceIcon html={currentWorkspace.icon_html} />
        ) : (
          <Avatar user={user} />
        )}
        {!collapsed && (
          <>
            <span
              className="flex-grow-1 text-start"
              style={{ minWidth: 0, overflow: "hidden" }}
            >
              <span
                className="d-block text-truncate fw-semibold"
                style={{ fontSize: "0.875rem" }}
              >
                {user.name}
              </span>
              {currentWorkspace && (
                <span
                  className="d-block text-truncate text-body-secondary"
                  style={{ fontSize: "0.75rem" }}
                >
                  {currentWorkspace.name}
                </span>
              )}
            </span>
            <i className="fa-regular fa-chevron-right text-muted small" />
          </>
        )}
      </button>
    </Tippy>
  );
}
