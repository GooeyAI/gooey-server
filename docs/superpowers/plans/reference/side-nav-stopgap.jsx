// REFERENCE ONLY — source design prototype for the NavigationSidebar feature.
// Imported from Claude Design project 3549168f-bb45-431c-8332-c1270664b8b5
// (file: side-nav-stopgap.jsx). This is the visual/interaction source of truth.
//
// PORT RULES (see the plan's Global Constraints):
//   - Hardcoded data (recents/saved/workspaces/user) becomes typed PROPS.
//   - Inline styles + var(--gy-*) become Bootstrap utility classes; colors map
//     to Bootstrap semantic classes (text-muted, bg-body, border, etc.), NOT
//     --gy-* vars. Layout/transition/scrollbar bits that Bootstrap can't express
//     go in NavigationSidebar.css.
//   - The TweaksPanel + useTweaks harness and the showIcons/showImages TOGGLES
//     are design-tooling only — DROP them. Bake in: show workflow images, fall
//     back to a FontAwesome icon when no image.
//   - The CommandPalette is DROPPED — search is just a rail item linking to the
//     Explore page (/explore/).
//   - The fa-bounce click animation is optional polish (CSS only); droppable.
//   - GooeyBot brand SVG stays inline.

const { useState, useEffect, useRef } = React;

/* ── Small atoms ──────────────────────────────────────────────────────── */
function Kbd({ children }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      minWidth: 18, height: 18, padding: "0 5px", borderRadius: 4,
      background: "var(--gy-surface-150)", fontFamily: "ui-monospace,Menlo,monospace",
      fontSize: 10.5, color: "var(--gy-ink-soft)", fontWeight: 500,
    }}>{children}</span>
  );
}

/* Gooey bot glyph (brand SVG) */
function GooeyBot({ size = 18 }) {
  return (
    <svg width={size} height={size * 210 / 278} viewBox="0 0 278 210" fill="none"
      xmlns="http://www.w3.org/2000/svg" style={{ display: "block" }}>
      <path fill="currentColor" d="M218.096 86.7852C223.618 86.7852 228.096 91.2625 228.096 96.7852V199.808C228.095 205.33 223.618 209.808 218.096 209.808H59.3584C53.8359 209.807 49.3586 205.33 49.3584 199.808V96.7852C49.3586 91.2626 53.8359 86.7854 59.3584 86.7852H218.096ZM38.5146 186.147H9C4.02955 186.147 0 182.118 0 177.147V120.858C0.000164041 115.888 4.02965 111.859 9 111.858H38.5146V186.147ZM268.455 111.858C273.426 111.858 277.455 115.888 277.455 120.858V177.147C277.455 182.118 273.426 186.147 268.455 186.147H238.94V111.858H268.455ZM92.457 130.898C82.7529 130.899 74.8859 138.766 74.8857 148.47C74.8857 158.174 82.7528 166.042 92.457 166.042C102.162 166.042 110.029 158.174 110.029 148.47C110.029 138.765 102.162 130.898 92.457 130.898ZM184.998 130.898C175.294 130.899 167.426 138.765 167.426 148.47C167.426 158.174 175.294 166.042 184.998 166.042C194.703 166.042 202.569 158.174 202.569 148.47C202.569 138.765 194.702 130.899 184.998 130.898ZM138.729 0C146.761 0.00018554 153.273 6.5121 153.273 14.5449C153.273 20.1275 150.128 24.9748 145.513 27.4131V81.5713H131.942V27.4121C127.328 24.9736 124.183 20.127 124.183 14.5449C124.183 6.51199 130.696 0 138.729 0Z"/>
    </svg>
  );
}

/* See the design project for the full prototype. Key structural facts the port
   must preserve (widths, sections, order):

   RAIL WIDTHS:  expanded 264px, collapsed 66px. Header height 56px.
   ORDER (top→bottom):
     1. Header: Mark (GooeyBot glyph + wordmark img) + collapse button (fa-sidebar).
        Collapsed: clicking the rail (outside buttons) expands; hovering shows
        an expand affordance on the glyph.
     2. Sticky "New" NavItem (fa-plus). → href = /explore2/
     3. Scroll region:
        - Home (fa-house), Explore (fa-magnifying-glass), Saved (fa-floppy-disk).
        - Saved is expandable: a nested, indented tree (with a 1px tree line at
          left:19px) of saved workflows (image/icon + label). Chevron on hover.
        - Recent section: a "Recent" label (collapsible, chevron on hover) then
          a list of recent workflow rows (image/icon + label, ellipsised).
        - When collapsed, Recent shows as a single NavItem (fa-clock-rotate-left);
          Saved tree + Recent list are hidden.
     4. Gooey Builder button (img assets/gooey-builder.png) just above footer.
        Render ONLY when can_launch_gooey_builder (recipe pages). Fires
        window.dispatchEvent(new CustomEvent("builder-sidebar:open")).
     5. Footer identity: avatar (letter or photo) + name + workspace name +
        chevron. Click opens UserMenu popover.

   NAV ITEM behavior: active item gets bold + a subtle surface background; hover
   gets a lighter surface; collapsed items center the icon and show a dark
   hover RailTooltip to the right. Active is driven by `active_key` prop.

   USER MENU popover (opens above the footer): a workspace selector row at top
   that opens a workspace submenu to the right (list of workspaces with a check
   on the current one + "Add workspace"); then menu rows: Profile, Billing,
   View all plans, Help, API, Docs, Log out. In the port these become real
   hrefs (menu_links + logout_href) and the workspace rows POST to the switch
   route. Anonymous: footer shows a "Sign In" row → /login instead of identity.

   RECENT/SAVED ROW: circular/rounded image (object-fit cover) OR a FontAwesome
   icon fallback, then an ellipsised label. Indented rows (Saved tree) sit under
   the tree line.
*/
