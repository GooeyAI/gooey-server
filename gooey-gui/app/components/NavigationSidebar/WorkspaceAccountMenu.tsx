import Tippy from "@tippyjs/react";
import clsx from "clsx";
import { useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import type { Placement } from "tippy.js";
import type {
  MenuLinkData,
  NavUserData,
  WorkspaceData,
} from "@gooey-types/navigation_sidebar_props";

const ACCOUNT_MENU_THEME = "account-menu";
const ACCOUNT_MENU_POPPER_OPTIONS = { strategy: "fixed" as const };
// Open the workspace switcher to the right, but flip below/left when it would
// overflow the viewport (e.g. the menu pinned to the right edge on mobile).
const WORKSPACE_SWITCHER_POPPER_OPTIONS = {
  modifiers: [
    {
      name: "flip",
      options: {
        fallbackPlacements: ["bottom-start", "left-start"],
      },
    },
  ],
};
const MENU_PANEL_CLASS =
  "account-menu-panel bg-body border shadow p-1 rounded-3";
const MENU_ROW_BASE_CLASS =
  "d-flex align-items-center gap-2 w-100 px-3 py-2 text-body text-decoration-none text-start border-0 rounded bg-hover-light";
const MENU_ROW_ACTION_CLASS = clsx(
  MENU_ROW_BASE_CLASS,
  "bg-transparent bg-hover-light"
);

type WorkspaceAccountMenuProps = {
  user: NavUserData;
  currentWorkspace: WorkspaceData | null;
  workspaces: WorkspaceData[];
  menuLinks: MenuLinkData[];
  logoutHref: string;
  onSwitchWorkspace: (workspaceId: number) => void;
  addWorkspaceOnClick: string;
  compact: boolean;
  placement?: Placement;
};

export function WorkspaceAccountMenu({
  user,
  currentWorkspace,
  workspaces,
  menuLinks,
  logoutHref,
  onSwitchWorkspace,
  addWorkspaceOnClick,
  compact,
  placement = "top-start",
}: WorkspaceAccountMenuProps) {
  const [open, setOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);

  const closeMenu = () => {
    setWorkspaceOpen(false);
    setOpen(false);
  };

  const accountLabel = currentWorkspace?.name || user.name;
  const menuContent = (
    <div className={MENU_PANEL_CLASS}>
      {currentWorkspace && (
        <>
          <Tippy
            visible={workspaceOpen}
            onClickOutside={() => setWorkspaceOpen(false)}
            interactive
            animation="scale"
            duration={120}
            placement="right-start"
            appendTo={() => document.body}
            zIndex={11001}
            popperOptions={WORKSPACE_SWITCHER_POPPER_OPTIONS}
            content={
              <WorkspaceSwitcher
                workspaces={workspaces}
                onSwitchWorkspace={onSwitchWorkspace}
                addWorkspaceOnClick={addWorkspaceOnClick}
                onSelect={closeMenu}
              />
            }
          >
            <button
              type="button"
              className={clsx(MENU_ROW_BASE_CLASS, "bg-body-secondary")}
              aria-haspopup="menu"
              aria-expanded={workspaceOpen}
              onClick={() => setWorkspaceOpen((isOpen) => !isOpen)}
            >
              <WorkspaceIcon html={currentWorkspace.icon_html} />
              <span className="flex-grow-1 text-truncate min-w-0">
                {currentWorkspace.name}
              </span>
              <i className="fa-regular fa-chevron-right text-body-secondary flex-shrink-0 small" />
            </button>
          </Tippy>
          <hr className="my-1" />
        </>
      )}

      {menuLinks.map((link) => (
        <AccountMenuItem
          key={`${link.href}:${link.label}`}
          href={link.href}
          icon={link.icon}
          onClick={closeMenu}
        >
          {link.label}
        </AccountMenuItem>
      ))}

      {logoutHref && (
        <>
          <hr className="my-1" />
          <AccountMenuItem
            href={logoutHref}
            icon="fa-regular fa-arrow-right-from-bracket"
            onClick={closeMenu}
          >
            Log out
          </AccountMenuItem>
        </>
      )}
    </div>
  );

  return (
    <Tippy
      visible={open}
      onClickOutside={closeMenu}
      interactive
      theme={ACCOUNT_MENU_THEME}
      animation="scale"
      duration={120}
      placement={placement}
      appendTo={() => document.body}
      zIndex={11000}
      arrow={false}
      offset={[0, 8]}
      maxWidth="none"
      popperOptions={ACCOUNT_MENU_POPPER_OPTIONS}
      content={menuContent}
    >
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setWorkspaceOpen(false);
          setOpen((isOpen) => !isOpen);
        }}
        className={clsx(
          "d-flex align-items-center border-0 bg-transparent text-body rounded p-2 bg-hover-light",
          compact ? "justify-content-center" : "w-100 gap-2"
        )}
        title={compact ? accountLabel : undefined}
      >
        {currentWorkspace ? (
          <WorkspaceIcon html={currentWorkspace.icon_html} />
        ) : (
          <Avatar user={user} />
        )}
        {!compact && (
          <>
            <span className="flex-grow-1 text-start overflow-hidden min-w-0">
              <span className="d-block text-truncate fw-semibold">
                {user.name}
              </span>
              {currentWorkspace && (
                <span className="d-block text-truncate text-body-secondary small">
                  {currentWorkspace.is_personal
                    ? "Personal"
                    : currentWorkspace.name}
                </span>
              )}
            </span>
            <i className="fa-regular fa-chevron-right text-body-secondary flex-shrink-0 small" />
          </>
        )}
      </button>
    </Tippy>
  );
}

function WorkspaceSwitcher({
  workspaces,
  onSwitchWorkspace,
  addWorkspaceOnClick,
  onSelect,
}: {
  workspaces: WorkspaceData[];
  onSwitchWorkspace: (workspaceId: number) => void;
  addWorkspaceOnClick: string;
  onSelect: () => void;
}) {
  return (
    <div className={MENU_PANEL_CLASS}>
      {workspaces.map((workspace) => (
        <WorkspaceMenuItem
          key={workspace.id}
          workspace={workspace}
          onSwitch={
            workspace.is_current
              ? undefined
              : () => onSwitchWorkspace(workspace.id)
          }
          onSelect={onSelect}
        />
      ))}
      {addWorkspaceOnClick && (
        <>
          <hr className="my-1" />
          <AccountMenuItem
            icon="fa-regular fa-plus"
            onClick={(event: MouseEvent<HTMLElement>) => {
              runGuiHandler(addWorkspaceOnClick, event);
              onSelect();
            }}
          >
            Add workspace
          </AccountMenuItem>
        </>
      )}
    </div>
  );
}

function runGuiHandler(js: string, event: MouseEvent<HTMLElement>) {
  if (!js) return;
  // eslint-disable-next-line no-new-func
  const fn = new Function("event", js);
  fn.call(event.currentTarget, event.nativeEvent);
}

function WorkspaceMenuItem({
  workspace,
  onSwitch,
  onSelect,
}: {
  workspace: WorkspaceData;
  onSwitch?: () => void;
  onSelect: () => void;
}) {
  const className = onSwitch
    ? MENU_ROW_ACTION_CLASS
    : clsx(
        MENU_ROW_BASE_CLASS,
        "pe-none",
        workspace.is_current && "bg-body-secondary"
      );
  const content = (
    <>
      <WorkspaceIcon html={workspace.icon_html} />
      <span className="flex-grow-1 min-w-0">
        <span className="d-block text-truncate fw-semibold">
          {workspace.name}
        </span>
        {workspace.subtitle && (
          <span className="d-block text-truncate text-body-secondary small">
            {workspace.subtitle}
          </span>
        )}
      </span>
      {workspace.is_current && (
        <i className="fa-solid fa-check text-body-secondary flex-shrink-0" />
      )}
    </>
  );

  if (onSwitch) {
    return (
      <button
        type="button"
        className={className}
        onClick={() => {
          onSwitch();
          onSelect();
        }}
      >
        {content}
      </button>
    );
  }

  return <div className={className}>{content}</div>;
}

function AccountMenuItem({
  href,
  icon,
  onClick,
  children,
}: {
  href?: string;
  icon?: string | null;
  onClick?: (event: MouseEvent<HTMLElement>) => void;
  children: ReactNode;
}) {
  const content = (
    <>
      <MenuIcon icon={icon} />
      <span className="flex-grow-1 text-truncate min-w-0">{children}</span>
    </>
  );

  if (href) {
    return (
      <a href={href} className={MENU_ROW_ACTION_CLASS} onClick={onClick}>
        {content}
      </a>
    );
  }

  return (
    <button type="button" className={MENU_ROW_ACTION_CLASS} onClick={onClick}>
      {content}
    </button>
  );
}

function MenuIcon({ icon }: { icon?: string | null }) {
  if (!icon) {
    return <span className="flex-shrink-0 account-menu-row-icon" />;
  }
  return (
    <i
      className={clsx(icon, "flex-shrink-0 text-center account-menu-row-icon")}
    />
  );
}

function WorkspaceIcon({ html }: { html: string }) {
  return (
    <span
      className="account-menu-icon d-inline-flex align-items-center justify-content-center flex-shrink-0 rounded-circle overflow-hidden"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function Avatar({ user }: { user: NavUserData }) {
  return (
    <img
      src={user.photo_url || ""}
      alt=""
      className="account-menu-avatar rounded-circle flex-shrink-0 object-fit-cover"
    />
  );
}
