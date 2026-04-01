import React, { useEffect, useRef, useState } from "react";
import type { HTMLReactParserOptions } from "html-react-parser";
import parse, {
  attributesToProps,
  domToReact,
  Element,
  Text,
} from "html-react-parser";
import { useHydratedMemo } from "~/useHydrated";
import { Link } from "@remix-run/react";
import type { TooltipPlacement } from "./components/GooeyTooltip";
import { GooeyHelpIcon } from "./components/GooeyTooltip";

export function RenderedHTML({
  body,
  lineClamp,
  help,
  tooltipPlacement,
  lineClampExpand,
  ...attrs
}: {
  body: string;
  lineClamp?: number;
  help?: string;
  tooltipPlacement?: TooltipPlacement;
  [attr: string]: any;
}) {
  if (attrs.renderLocalDt) {
    return <RenderLocalDt body={body} {...attrs} />;
  }

  if (typeof body !== "string") {
    body = JSON.stringify(body);
  }
  let parsedElements = parse(body || "", reactParserOptions);
  if (help) {
    parsedElements = (
      <div>
        <div className="d-flex align-items-baseline position-relative">
          <div>{parsedElements}</div>
          <GooeyHelpIcon content={help} placement={tooltipPlacement} />
        </div>
      </div>
    );
  }
  return (
    <LineClamp lines={lineClamp} key={body} expandable={lineClampExpand}>
      <span className="gui-html-container" {...attrs}>
        {parsedElements}
      </span>
    </LineClamp>
  );
}

function RenderLocalDt({
  body,
  renderLocalDt,
  renderLocalDtDateOptions,
  renderLocalDtTimeOptions,
  ...attrs
}: {
  body: string;
  [attr: string]: any;
}) {
  const [body2, setBody] = useState(body);

  useEffect(() => {
    const date = new Date(renderLocalDt);
    let yearToShow = "";
    if (date.getFullYear() != new Date().getFullYear()) {
      yearToShow = " " + date.getFullYear().toString();
    }
    const localeDateString = date.toLocaleDateString(
      "en-IN",
      renderLocalDtDateOptions
    );
    let result = localeDateString + yearToShow;
    if (renderLocalDtTimeOptions) {
      const localTimeString = date
        .toLocaleTimeString("en-IN", renderLocalDtTimeOptions)
        .toUpperCase();
      result += ", " + localTimeString;
    }
    setBody(result);
  }, [body, renderLocalDt, renderLocalDtDateOptions, renderLocalDtTimeOptions]);

  const parsedElements = parse(body2, reactParserOptions);
  return (
    <span className="gui-html-container" {...attrs}>
      {parsedElements}
    </span>
  );
}

const reactParserOptions: HTMLReactParserOptions = {
  htmlparser2: {
    lowerCaseTags: false,
    lowerCaseAttributeNames: false,
  },
  replace: function (domNode) {
    if (!(domNode instanceof Element && domNode.attribs)) return;

    if (
      domNode.children.length &&
      domNode.children[0] instanceof Element &&
      domNode.children[0].name === "code" &&
      domNode.children[0].attribs.class?.includes("language-")
    ) {
      return (
        <RenderedPrismCode domNode={domNode} options={reactParserOptions} />
      );
    }

    if (typeof domNode.attribs["data-internal-link"] !== "undefined") {
      const href = domNode.attribs.href;
      delete domNode.attribs.href;
      return (
        <Link to={href} {...attributesToProps(domNode.attribs)}>
          {domToReact(domNode.children, reactParserOptions)}
        </Link>
      );
    }

    for (const [attr, value] of Object.entries(domNode.attribs)) {
      if (!attr.startsWith("on")) continue;
      delete domNode.attribs[attr];
      const reactAttrName = "on" + attr[2].toUpperCase() + attr.slice(3);
      // @ts-ignore
      domNode.attribs[reactAttrName] = (event: React.SyntheticEvent) => {
        // eslint-disable-next-line no-new-func
        const fn = new Function("event", value);
        return fn.call(event.currentTarget, event.nativeEvent);
      };
    }

    if (domNode.type === "script") {
      let body = getTextBody(domNode);
      return <InlineScript attrs={domNode.attribs} body={body} />;
    }
  },
};

function LineClamp({
  lines,
  children,
  expandable = true,
}: {
  lines?: number;
  children: React.ReactNode;
  expandable: boolean;
}) {
  const contentRef = useRef<HTMLSpanElement>(null);

  const [isClamped, setClamped] = useState(false);
  const [isExpanded, setExpanded] = useState(false);

  useEffect(() => {
    // Function that should be called on window resize
    function handleResize() {
      if (contentRef && contentRef.current) {
        setClamped(
          contentRef.current.scrollHeight > contentRef.current.clientHeight
        );
      }
    }

    handleResize();

    // Add event listener to window resize
    window.addEventListener("resize", handleResize);

    // Remove event listener on cleanup
    return () => window.removeEventListener("resize", handleResize);
  }, []); // Empty array ensures that it would only run on mount

  if (!lines) {
    return <>{children}</>;
  }

  return (
    <span
      ref={contentRef}
      style={{
        ...(isExpanded
          ? {}
          : {
              display: "-webkit-box",
              WebkitLineClamp: lines,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
              position: "relative",
            }),
      }}
    >
      {children}
      {isExpanded || !isClamped ? (
        <></>
      ) : (
        <span
          style={{
            position: "absolute",
            bottom: 0,
            right: 0,
            padding: "0 0 0 .4rem",
            lineHeight: "130%",
          }}
        >
          {expandable && (
            <button
              style={{
                border: "none",
                backgroundColor: "white",
                color: "rgba(0, 0, 0, 0.6)",
              }}
              type={"button"}
              onClick={() => {
                setExpanded(true);
              }}
            >
              …more
            </button>
          )}
        </span>
      )}
    </span>
  );
}
const SCRIPTS_LOADED: Record<string, boolean> = {};

function InlineScript({
  attrs,
  body,
}: {
  attrs?: Record<string, string>;
  body: string;
}) {
  const hydrated = useHydratedMemo();
  const oldRef = useRef<HTMLScriptElement>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (oldRef.current) {
      SCRIPTS_LOADED[oldRef.current.outerHTML] = true;
    }
    if (!ref.current) return;
    // create script tag
    const script = document.createElement("script");
    // add attribs
    for (const [attr, value] of Object.entries(attrs ?? {})) {
      script.setAttribute(attr, value);
    }
    // add inline script
    if (body) {
      script.appendChild(document.createTextNode(body));
    }
    // ensure that the script is only added once by checking if it is the same
    if (SCRIPTS_LOADED[script.outerHTML]) return;
    SCRIPTS_LOADED[script.outerHTML] = true;
    // append script to div
    ref.current.replaceChildren(script);
  }, [body, attrs]);

  if (hydrated) {
    return <div ref={ref} className="d-none"></div>;
  } else {
    return (
      <script
        ref={oldRef}
        {...attributesToProps(attrs ?? {}, "script")}
        dangerouslySetInnerHTML={{ __html: body }}
      />
    );
  }
}

function RenderedPrismCode({
  domNode,
  options,
}: {
  domNode: Element;
  options: HTMLReactParserOptions;
}) {
  const ref = useRef<HTMLElement>(null);
  const body = getTextBody(domNode);
  useEffect(() => {
    // @ts-ignore
    if (!ref.current || !window.Prism) return;
    // @ts-ignore
    window.Prism.highlightElement(ref.current);
  }, [body]);
  // @ts-ignore
  domNode.children[0].attribs.ref = ref;
  return (
    <span className="gui-html-container">
      <pre key={body} {...attributesToProps(domNode.attribs)}>
        {domToReact(domNode.children, options)}
      </pre>
    </span>
  );
}

function getTextBody(domNode: Element) {
  let body = "";
  const child = domNode.children[0];
  if (child instanceof Text) {
    body = child.data;
  }
  return body;
}
