import { useEffect } from "react";
import { Link } from "@remix-run/react";

/** One row of the sheet. Either a link (`href`) or an action (`onPick`), never both. */
export type SheetEntry = {
  key: string;
  label: string;
  /** Raw FontAwesome html when the server supplied one (view icons), else a class name. */
  iconHtml?: string;
  iconClass?: string;
  href?: string;
  onPick?: () => void;
  /** A group label rather than a row you can press - it names the entries under it. */
  heading?: boolean;
};

/** The mobile view switcher and action list, as a bottom sheet.
 *
 * Below lg this replaces the floating pill strip. The strip could only ever offer the panes -
 * About, Edit, Preview - whereas the sheet is a list, so it also carries the actions that had
 * nowhere to live once the sidebar's mobile bar went away. It is the reason the header needs
 * only two controls.
 *
 * Deliberately not a `<dialog>`: the sheet has to sit under the nav drawer in the stacking
 * order (both can be open in principle, and the drawer is the outer surface), and a top-layer
 * dialog always paints above everything regardless of z-index.
 */
export function MobileActionSheet({
  entries,
  onDismiss,
}: {
  entries: SheetEntry[];
  onDismiss: () => void;
}) {
  // Escape closes it. Pointer dismissal is the scrim's job below - it covers the whole
  // viewport, so a click anywhere outside the sheet lands on it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDismiss();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onDismiss]);

  if (!entries.length) return null;

  return (
    <div
      className="gooey-sheet-scrim"
      // The scrim is the dismiss target, not a control: it carries no name and no role, so
      // assistive tech sees the sheet's own buttons and nothing else.
      onClick={onDismiss}
    >
      <div
        className="gooey-sheet"
        role="menu"
        aria-label="Workflow menu"
        // without this a tap inside the sheet bubbles to the scrim and closes it
        onClick={(e) => e.stopPropagation()}
      >
        {/* Purely a grab affordance - it says "this surface came up from the bottom and can
            go back down". Not focusable, and hidden from the tree, because Escape and the
            scrim are what actually dismiss. */}
        <div className="gooey-sheet-handle-wrap" aria-hidden="true">
          <div className="gooey-sheet-handle" />
        </div>

        {entries.map((entry) => {
          // A label, so it takes no icon slot and no click. Rendered as a heading rather than
          // skipped: it is what stops a long list of channels reading as more actions.
          if (entry.heading) {
            return (
              <div key={entry.key} className="gooey-sheet-heading">
                {entry.label}
              </div>
            );
          }
          const inner = (
            <>
              <span className="gooey-sheet-icon">
                {entry.iconHtml ? (
                  <span dangerouslySetInnerHTML={{ __html: entry.iconHtml }} />
                ) : (
                  <i className={entry.iconClass} />
                )}
              </span>
              {entry.label}
            </>
          );
          return entry.href ? (
            <Link
              key={entry.key}
              to={entry.href}
              className="gooey-sheet-item"
              role="menuitem"
              // A link entry may still have side effects to run before it navigates - putting
              // Ask Gooey away, in every current case - so `onPick` fires here too rather than
              // being treated as the alternative to `href`.
              onClick={() => {
                entry.onPick?.();
                onDismiss();
              }}
            >
              {inner}
            </Link>
          ) : (
            <button
              key={entry.key}
              type="button"
              className="gooey-sheet-item"
              role="menuitem"
              onClick={() => {
                entry.onPick?.();
                onDismiss();
              }}
            >
              {inner}
            </button>
          );
        })}
      </div>
    </div>
  );
}
