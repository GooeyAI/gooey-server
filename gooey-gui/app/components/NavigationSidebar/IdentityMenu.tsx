import { useEffect, useRef, useState } from "react";
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

function MenuRow({
  href,
  icon,
  iconHtml,
  children,
  trailing,
}: {
  href?: string;
  icon?: string | null;
  iconHtml?: string;
  children: React.ReactNode;
  trailing?: React.ReactNode;
}) {
  const inner = (
    <>
      {iconHtml ? (
        <span
          className="d-inline-flex align-items-center justify-content-center flex-shrink-0"
          style={{ width: 22 }}
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
      ) : icon ? (
        <i
          className={icon}
          style={{ width: 22, textAlign: "center", flexShrink: 0 }}
        />
      ) : (
        <span style={{ width: 22, flexShrink: 0 }} />
      )}
      <span className="flex-grow-1 text-truncate" style={{ minWidth: 0 }}>
        {children}
      </span>
      {trailing}
    </>
  );

  const className =
    "d-flex align-items-center gap-2 px-3 py-2 text-body text-decoration-none";

  if (href) {
    return (
      <a href={href} className={className + " bg-hover-light"}>
        {inner}
      </a>
    );
  }
  return <div className={className}>{inner}</div>;
}

export function IdentityMenu({
  user,
  currentWorkspace,
  workspaces,
  menuLinks,
  logoutHref,
  switchWorkspaceHref,
  collapsed,
}: {
  user: NavUserData;
  currentWorkspace: WorkspaceData | null;
  workspaces: WorkspaceData[];
  menuLinks: MenuLinkData[];
  logoutHref: string;
  switchWorkspaceHref: string;
  collapsed: boolean;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [open]);

  return (
    <div className="identity-menu-wrap position-relative" ref={wrapRef}>
      {open && (
        <div className="identity-menu bg-body border rounded shadow overflow-auto">
          {workspaces.length > 0 && (
            <>
              {workspaces.map((ws) => (
                <MenuRow
                  key={ws.id}
                  href={
                    ws.is_current
                      ? undefined
                      : switchWorkspaceHref.replace(
                          "{workspace_id}",
                          String(ws.id),
                        )
                  }
                  iconHtml={ws.icon_html}
                  trailing={
                    ws.is_current ? (
                      <i className="fa-solid fa-circle-check text-body-secondary" />
                    ) : undefined
                  }
                >
                  {ws.name}
                </MenuRow>
              ))}
              <hr className="my-1" />
            </>
          )}

          {menuLinks.map((link, i) => (
            <MenuRow key={i} href={link.href} icon={link.icon}>
              {link.label}
            </MenuRow>
          ))}

          {logoutHref && (
            <>
              <hr className="my-1" />
              <MenuRow href={logoutHref} icon="fa-regular fa-sign-out">
                Log out
              </MenuRow>
            </>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={[
          "identity-btn d-flex align-items-center w-100 border-0 bg-transparent text-body rounded p-2 bg-hover-light",
          collapsed ? "justify-content-center" : "gap-2",
        ].join(" ")}
        title={collapsed ? user.name : undefined}
      >
        <Avatar user={user} />
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
            <i
              className="fa-regular fa-chevron-up text-body-secondary"
              style={{ fontSize: 11 }}
            />
          </>
        )}
      </button>
    </div>
  );
}
