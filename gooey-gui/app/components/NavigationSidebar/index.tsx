import "./NavigationSidebar.css";

import type { CustomComponentProps } from "~/components";
import type { NavigationSidebarProps } from "@gooey-types/navigation_sidebar_props";

function GooeyBot({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={(size * 210) / 278}
      viewBox="0 0 278 210"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: "block" }}
    >
      <path
        fill="currentColor"
        d="M218.096 86.7852C223.618 86.7852 228.096 91.2625 228.096 96.7852V199.808C228.095 205.33 223.618 209.808 218.096 209.808H59.3584C53.8359 209.807 49.3586 205.33 49.3584 199.808V96.7852C49.3586 91.2626 53.8359 86.7854 59.3584 86.7852H218.096ZM38.5146 186.147H9C4.02955 186.147 0 182.118 0 177.147V120.858C0.000164041 115.888 4.02965 111.859 9 111.858H38.5146V186.147ZM268.455 111.858C273.426 111.858 277.455 115.888 277.455 120.858V177.147C277.455 182.118 273.426 186.147 268.455 186.147H238.94V111.858H268.455ZM92.457 130.898C82.7529 130.899 74.8859 138.766 74.8857 148.47C74.8857 158.174 82.7528 166.042 92.457 166.042C102.162 166.042 110.029 158.174 110.029 148.47C110.029 138.765 102.162 130.898 92.457 130.898ZM184.998 130.898C175.294 130.899 167.426 138.765 167.426 148.47C167.426 158.174 175.294 166.042 184.998 166.042C194.703 166.042 202.569 158.174 202.569 148.47C202.569 138.765 194.702 130.899 184.998 130.898ZM138.729 0C146.761 0.00018554 153.273 6.5121 153.273 14.5449C153.273 20.1275 150.128 24.9748 145.513 27.4131V81.5713H131.942V27.4121C127.328 24.9736 124.183 20.127 124.183 14.5449C124.183 6.51199 130.696 0 138.729 0Z"
      />
    </svg>
  );
}

export function NavigationSidebar({
  logo_image_url,
  nav_items,
  active_key,
  new_href,
}: CustomComponentProps & NavigationSidebarProps) {
  return (
    <nav className="nav-sidebar d-flex flex-column p-2 border-end bg-body">
      {/* Header: logo + GooeyBot glyph */}
      <div className="d-flex align-items-center gap-2 p-2 mb-1" style={{ height: 56 }}>
        <a href="/" className="d-flex align-items-center gap-2 text-body text-decoration-none">
          <GooeyBot size={24} />
          <img
            src={logo_image_url}
            alt="Gooey.AI"
            height={22}
            className="img-fluid"
          />
        </a>
      </div>

      {/* Sticky "New" button */}
      <a
        href={new_href}
        className="btn btn-primary d-flex align-items-center gap-2 mb-2 fw-semibold"
      >
        <i className="fa-regular fa-plus" />
        New
      </a>

      {/* Primary nav items */}
      <div className="d-flex flex-column gap-1">
        {nav_items.map((item) => {
          const isActive = item.key === active_key;
          return (
            <a
              key={item.key}
              href={item.href}
              className={[
                "d-flex align-items-center gap-2 px-2 py-2 rounded text-decoration-none",
                isActive
                  ? "fw-bold bg-body-secondary text-body"
                  : "text-body",
              ].join(" ")}
            >
              <i className={item.icon} style={{ width: 18, textAlign: "center" }} />
              <span>{item.label}</span>
            </a>
          );
        })}
      </div>

      {/* Later tasks: recent/saved lists, identity menu, builder button — stubbed */}
    </nav>
  );
}
