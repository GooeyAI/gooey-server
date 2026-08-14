import clsx from "clsx";
import type { NavAccountData } from "@gooey-types/navigation_sidebar_props";
import type { Placement } from "tippy.js";
import { GoogleSignInButton } from "./GoogleSignInButton";
import { WorkspaceAccountMenu } from "./WorkspaceAccountMenu";

export function AccountSection({
  account,
  onSwitchWorkspace,
  compact,
  placement,
  mobile = false,
}: {
  account: NavAccountData;
  onSwitchWorkspace: (workspaceId: number) => void;
  compact: boolean;
  placement: Placement;
  mobile?: boolean;
}) {
  if (account.user) {
    return (
      <WorkspaceAccountMenu
        account={account}
        onSwitchWorkspace={onSwitchWorkspace}
        compact={compact}
        placement={placement}
      />
    );
  }

  return (
    <SignedOutAccount account={account} compact={compact} mobile={mobile} />
  );
}

export function SignedOutAccount({
  account,
  compact,
  mobile,
}: {
  account: NavAccountData;
  compact: boolean;
  mobile: boolean;
}) {
  // Mobile top bar and the off-canvas drawer: send users to /login/ instead of
  // rendering GSI's iframe button. The drawer is CSS-transformed, which makes
  // that iframe navigate to a malformed accounts.google.com URL on iOS (400).
  if (mobile) {
    return <SignInLink href={account.login_href} />;
  }

  // Collapsed rail (narrow, vertical): room for a single icon-sized affordance.
  if (compact) {
    if (account.enable_firebase_auth) return <GoogleSignInButton compact />;
    return <SignInLink href={account.login_href} iconOnly />;
  }

  // Expanded rail: full Google button + subtle "Sign In" link (or just the link
  // when Firebase auth is off).
  if (account.enable_firebase_auth) {
    return (
      <div className="d-flex flex-column align-items-stretch gap-1">
        <GoogleSignInButton compact={false} />
        <SignInLink href={account.login_href} subtle block />
      </div>
    );
  }
  return <SignInLink href={account.login_href} block />;
}

function SignInLink({
  href,
  iconOnly = false,
  subtle = false,
  block = false,
}: {
  href: string;
  iconOnly?: boolean;
  subtle?: boolean;
  block?: boolean;
}) {
  return (
    <a
      href={href}
      className={clsx(
        "d-flex align-items-center justify-content-center text-decoration-none rounded p-2 bg-hover-light position-relative",
        !iconOnly && "gap-2",
        block && "w-100",
        subtle ? "small" : "text-body"
      )}
      title={iconOnly ? "Sign In" : undefined}
    >
      {iconOnly ? (
        <i className="fa-regular fa-arrow-right-to-bracket" />
      ) : (
        <span className={clsx(!subtle && "fw-semibold")}>Sign In</span>
      )}
    </a>
  );
}
