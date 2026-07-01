import Tippy from "@tippyjs/react";
import clsx from "clsx";
import { useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import type { Placement } from "tippy.js";
import type {
  NavAccountData,
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

export function WorkspaceAccountMenu({
  account,
  onSwitchWorkspace,
  compact,
  placement = "top-start",
}: {
  account: NavAccountData;
  onSwitchWorkspace: (workspaceId: number) => void;
  compact: boolean;
  placement?: Placement;
}) {
  const [open, setOpen] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);

  // The menu only renders for signed-in users; bail out otherwise so the rest
  // can rely on `account.user` being present.
  if (!account.user) return null;

  const closeMenu = () => {
    setWorkspaceOpen(false);
    setOpen(false);
  };

  const accountLabel = account.current_workspace?.name || account.user.name;
  const menuContent = (
    <div className={MENU_PANEL_CLASS}>
      {account.current_workspace && (
        <>
          <Tippy
            visible={workspaceOpen}
            onClickOutside={() => setWorkspaceOpen(false)}
            interactive
            animation="scale"
            duration={120}
            placement="right-start"
            zIndex={11001}
            popperOptions={WORKSPACE_SWITCHER_POPPER_OPTIONS}
            content={
              <WorkspaceSwitcher
                account={account}
                onSwitchWorkspace={onSwitchWorkspace}
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
              <WorkspaceIcon html={account.current_workspace.icon_html} />
              <span className="flex-grow-1 text-truncate min-w-0">
                {account.current_workspace.name}
              </span>
              <i className="fa-regular fa-chevron-right text-body-secondary flex-shrink-0 small" />
            </button>
          </Tippy>
          <hr className="my-1" />
        </>
      )}

      {account.menu_links.map((link) => (
        <AccountMenuItem
          key={`${link.href}:${link.label}`}
          href={link.href}
          icon={link.icon}
          onClick={closeMenu}
        >
          {link.label}
        </AccountMenuItem>
      ))}

      {account.logout_href && (
        <>
          <hr className="my-1" />
          <AccountMenuItem
            href={account.logout_href}
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
        {account.current_workspace ? (
          <WorkspaceIcon html={account.current_workspace.icon_html} />
        ) : (
          <Avatar user={account.user} />
        )}
        {!compact && (
          <>
            <span className="flex-grow-1 text-start overflow-hidden min-w-0">
              <span className="d-block text-truncate fw-semibold">
                {account.user.name}
              </span>
              {account.current_workspace && (
                <span className="d-block text-truncate text-body-secondary small">
                  {account.current_workspace.is_personal
                    ? "Personal"
                    : account.current_workspace.name}
                </span>
              )}
            </span>
          </>
        )}
      </button>
    </Tippy>
  );
}

function WorkspaceSwitcher({
  account,
  onSwitchWorkspace,
  onSelect,
}: {
  account: NavAccountData;
  onSwitchWorkspace: (workspaceId: number) => void;
  onSelect: () => void;
}) {
  return (
    <div className={MENU_PANEL_CLASS}>
      {account.workspaces.map((workspace) => (
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
      {account.add_workspace_url && (
        <>
          <hr className="my-1" />
          <AccountMenuItem
            icon="fa-regular fa-plus"
            href={account.add_workspace_url}
            target="_blank"
            onClick={onSelect}
          >
            Add workspace
          </AccountMenuItem>
        </>
      )}
    </div>
  );
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
          onSelect(); // close the menu
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
  target,
  icon,
  onClick,
  children,
}: {
  href?: string;
  target?: string;
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
      <a
        href={href}
        target={target}
        rel={target === "_blank" ? "noopener" : undefined}
        className={MENU_ROW_ACTION_CLASS}
        onClick={onClick}
      >
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
