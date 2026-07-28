import { Link } from "@remix-run/react";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

// Rail links navigate client-side, so the sidebar keeps its React state (open
// sections, the fetched History list) instead of being torn down and rebuilt on
// every page change. Plain <a> tags trigger a document load, which is what makes
// the whole rail flash.
//
// Link takes our absolute urls as-is: it strips the origin off same-origin ones
// and leaves anything external (docs, blog) to navigate normally.
export function NavLink({
  href,
  children,
  ...props
}: {
  href?: string | null;
  children?: ReactNode;
} & Omit<ComponentPropsWithoutRef<"a">, "href" | "children">) {
  // sections without a destination of their own still render as a row
  if (!href) {
    return <a {...props}>{children}</a>;
  }
  return (
    <Link to={href} {...props}>
      {children}
    </Link>
  );
}
