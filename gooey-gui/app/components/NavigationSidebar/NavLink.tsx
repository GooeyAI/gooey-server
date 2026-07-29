import { Link } from "@remix-run/react";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

// Rail links navigate client-side, so the sidebar keeps its React state (open
// sections, the fetched History list) instead of being torn down and rebuilt on
// every page change. Plain <a> tags trigger a document load, which is what makes
// the whole rail flash.
export function NavLink({
  href,
  children,
  state,
  ...props
}: {
  href?: string | null;
  children?: ReactNode;
  state?: unknown;
} & Omit<ComponentPropsWithoutRef<"a">, "href" | "children">) {
  // sections without a destination of their own still render as a row
  if (!href) {
    return <a {...props}>{children}</a>;
  }
  return (
    <Link to={href} state={state} {...props}>
      {children}
    </Link>
  );
}
