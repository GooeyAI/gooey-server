import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
import { RenderedMarkdown } from "~/renderedMarkdown";

import { Tab, TabList, TabPanel, TabPanels, Tabs } from "@reach/tabs";
import { Link, useLocation } from "@remix-run/react";
import { JsonViewer } from "@textea/json-viewer";
import { DownloadButton } from "~/downloadButton";
import {
  GooeyCheckbox,
  GooeyInput,
  GooeyRadio,
  GooeyTextarea,
  InputLabel,
  loadEventHandlers,
} from "~/gooeyInput";
import { RenderedHTML } from "~/renderedHTML";
import type { OnChange } from "./app";
import CountdownTimer from "./components/countdown";
import GooeyPopover from "./components/GooeyPopover";
import GooeySelect from "./components/GooeySelect";
import GooeySwitch from "./components/GooeySwitch";
import { GooeyTooltip } from "./components/GooeyTooltip";
import GooeySidebar from "./components/Sidebar";
import { lazyImport } from "./lazyImports";

const { DataTable } = lazyImport(() => import("~/dataTable"));

const { GooeyFileInput } = lazyImport(() => import("~/gooeyFileInput"), {
  fallback: ({ name, label, defaultValue }) => (
    <div className="gui-input">
      <InputLabel label={label} />
      <input
        type="hidden"
        name={name}
        value={JSON.stringify(defaultValue)}
        readOnly
      />
      <div
        className="d-flex align-items-center justify-content-center bg-light"
        style={{ height: "250px" }}
      >
        Loading...
      </div>
    </div>
  ),
});

const Plot = lazyImport(
  () => import("react-plotly.js").then((mod) => mod.default)
  // @ts-ignore
).default;

const CodeEditor = lazyImport(() => import("./components/CodeEditor"), {
  fallback: ({ props }) => {
    return (
      <div className="gui-input">
        <InputLabel label={props.label} />
        <div
          className="d-flex align-items-center justify-content-center"
          style={{
            height: (props.defaultValue || "").split("\n").length * 1.5 + "rem",
            ...props.style,
          }}
        >
          Loading...
        </div>
      </div>
    );
  },
}).default;

export type TreeNode = {
  name: string;
  props: Record<string, any>;
  children: Array<TreeNode>;
};

export function applyFormDataTransforms({
  children,
  formData,
}: {
  children: Array<TreeNode>;
  formData: Record<string, FormDataEntryValue | null>;
}) {
  for (const node of children) {
    const { name, props, children } = node;
    if (children) {
      applyFormDataTransforms({ children, formData });
    }
    let type;
    if (name === "input") {
      type = props.type;
    } else {
      type = name;
    }
    let transform = formDataTransforms[type];
    if (!transform) continue;
    formData[props.name] = transform(formData[props.name]);
  }
}

const formDataTransforms: Record<
  string,
  (val: FormDataEntryValue | null) => any
> = {
  checkbox: Boolean,
  switch: Boolean,
  number: parseIntFloat,
  range: parseIntFloat,
  select: parseJSON,
  file: parseJSON,
};

function parseJSON(val: FormDataEntryValue | null) {
  if (!val) return null;
  return JSON.parse(val.toString());
}

function parseIntFloat(
  val: FormDataEntryValue | undefined | null
): number | undefined {
  if (!val) return undefined;
  let strVal = val.toString();
  const intVal = parseInt(strVal);
  const floatVal = parseFloat(strVal);
  if (floatVal == intVal) {
    return intVal;
  } else if (isNaN(floatVal)) {
    return 0;
  } else {
    return floatVal;
  }
}

function RenderedTreeNode({
  node,
  onChange,
  state,
}: {
  node: TreeNode;
  onChange: OnChange;
  state: Record<string, any>;
}) {
  const { name, props, children } = node;
  loadEventHandlers(undefined, undefined, props);

  switch (name) {
    case "":
      return (
        <RenderedChildren
          children={children}
          onChange={onChange}
          state={state}
          className={props.className}
        />
      );
    case "nav-tab-content":
      return (
        <div className="tab-content">
          <div className="tab-pane show active" role="tabpanel">
            <RenderedChildren
              children={children}
              onChange={onChange}
              state={state}
            />
          </div>
        </div>
      );
    case "data-table": {
      return (
        <DataTable {...props} onChange={onChange} state={state}></DataTable>
      );
    }
    case "nav-tabs":
      return (
        <ul
          className="nav justify-content-md-start justify-content-evenly nav-tabs"
          role="tablist"
          {...props}
        >
          <RenderedChildren
            children={children}
            onChange={onChange}
            state={state}
          />
        </ul>
      );
    case "nav-item": {
      const { to, active, ...args } = props;
      return (
        <Link to={to} {...args}>
          <li className="nav-item" role="presentation">
            <button
              className={`nav-link  p-2 px-md-3 py-md-2  mx-0 mx-md-2 ${active ? "active" : ""
                }`}
              type="button"
              role="tab"
              aria-controls="run"
              aria-selected="true"
            >
              <p className="mb-0">
                <RenderedChildren
                  children={children}
                  onChange={onChange}
                  state={state}
                />
              </p>
            </button>
          </li>
        </Link>
      );
    }
    case "pre": {
      const { body, ...args } = props;
      return (
        <pre className="gooey-output-text" {...args}>
          {body}
        </pre>
      );
    }
    case "ul": {
      return (
        <ul {...props}>
          <RenderedChildren
            children={children}
            onChange={onChange}
            state={state}
          />
        </ul>
      );
    }
    case "div": {
      return (
        <div {...props}>
          <RenderedChildren
            children={children}
            onChange={onChange}
            state={state}
          />
        </div>
      );
    }
    case "tabs":
      const tabs = children.map((elem) => (
        <Tab key={elem.props.label}>
          <RenderedMarkdown body={elem.props.label} state={state} />
        </Tab>
      ));
      const panels = children.map((elem) => (
        <TabPanel key={elem.props.label} {...elem.props}>
          <RenderedChildren
            children={elem.children}
            onChange={onChange}
            state={state}
          />
        </TabPanel>
      ));
      return (
        <Tabs {...props}>
          <TabList>{tabs}</TabList>
          <TabPanels>{panels}</TabPanels>
        </Tabs>
      );
    case "expander": {
      return (
        <GuiExpander onChange={onChange} state={state} {...props}>
          <RenderedChildren
            children={children}
            onChange={onChange}
            state={state}
          />
        </GuiExpander>
      );
    }
    case "img": {
      const { caption, href, ...args } = props;
      let child = (
        <>
          <RenderedMarkdown body={caption} />
          <img
            className="gui-img"
            alt={caption}
            {...args}
            onClick={() => {
              if (href || args.src.startsWith("data:")) return;
              window.open(args.src);
            }}
          />
        </>
      );
      if (href) {
        child = (
          <Link to={href}>
            <div>{child}</div>
          </Link>
        );
      }
      return child;
    }
    case "video": {
      const { caption, ...args } = props;
      return (
        <>
          <RenderedMarkdown body={caption} />
          <video className="gui-video" controls {...args}></video>
        </>
      );
    }
    case "audio": {
      const { caption, ...args } = props;
      return (
        <>
          <RenderedMarkdown body={caption} />
          <audio className="gui-audio" controls {...args}></audio>
        </>
      );
    }
    case "html": {
      const { body, help, tooltipPlacement, ...args } = props;
      return (
        <RenderedHTML
          body={body}
          help={help}
          tooltipPlacement={tooltipPlacement}
          {...args}
        />
      );
    }
    case "markdown": {
      const { body, lineClamp, help, tooltipPlacement, ...args } = props;
      return (
        <RenderedMarkdown
          body={body}
          lineClamp={lineClamp}
          help={help}
          tooltipPlacement={tooltipPlacement}
          {...args}
        />
      );
    }
    case "textarea": {
      return <GooeyTextarea props={props} state={state} />;
    }
    case "code-editor": {
      return <CodeEditor props={props} state={state} onChange={onChange} />;
    }
    case "switch":
      return <GooeySwitch props={props} state={state} />;
    case "input": {
      const className = `gui-input gui-input-${props.type}`;
      const id = inputId(props);
      switch (props.type) {
        case "range":
          return (
            <GooeySlider
              className={className}
              id={id}
              props={props}
              state={state}
            />
          );
        case "file":
          return (
            <GooeyFileInput
              name={props.name}
              label={props.label}
              accept={props.accept}
              multiple={props.multiple}
              defaultValue={props.defaultValue}
              uploadMeta={props.uploadMeta}
              help={props.help}
              tooltipPlacement={props.tooltipPlacement}
            />
          );
        case "checkbox":
          return (
            <GooeyCheckbox
              props={props}
              id={id}
              state={state}
              className={className}
            ></GooeyCheckbox>
          );
        case "radio":
          return (
            <GooeyRadio
              props={props}
              id={id}
              state={state}
              className={className}
            ></GooeyRadio>
          );
        default:
          return (
            <GooeyInput
              props={props}
              id={id}
              state={state}
              className={className}
            ></GooeyInput>
          );
      }
    }
    case "gui-button": {
      const { label, ...args } = props;
      return (
        <button type="button" {...args}>
          <RenderedMarkdown body={label} />
        </button>
      );
    }
    case "download-button": {
      const { label, url, ...args } = props;
      return <DownloadButton label={label} url={url} {...args} />;
    }
    case "select":
      return <GooeySelect props={props} onChange={onChange} state={state} />;
    case "option": {
      const { label, ...args } = props;
      return (
        <option {...args}>{label && <RenderedMarkdown body={label} />}</option>
      );
    }
    case "json":
      return (
        <JsonViewer
          style={{
            overflow: "scroll",
            marginTop: "1rem",
            whiteSpace: "pre-wrap",
          }}
          rootName={false}
          value={props.value}
          defaultInspectDepth={props.defaultInspectDepth}
          {...props}
        />
      );
    case "Link":
      return (
        <Link to={props.to} {...props}>
          <RenderedChildren
            children={children}
            onChange={onChange}
            state={state}
          />
        </Link>
      );
    case "tag": {
      const { __reactjsxelement, ...args } = props;
      if (children.length) {
        return (
          <__reactjsxelement {...args}>
            <RenderedChildren
              children={children}
              onChange={onChange}
              state={state}
            />
          </__reactjsxelement>
        );
      } else {
        return <__reactjsxelement {...args} />;
      }
    }
    case "countdown-timer": {
      return (
        <CountdownTimer endTime={props.endTime} delayText={props.delayText}>
          <RenderedChildren
            children={children}
            onChange={onChange}
            state={state}
          />
        </CountdownTimer>
      );
    }
    case "script": {
      const { src, args } = props;
      return <ExecJs state={state} src={src} args={args}></ExecJs>;
    }
    case "plotly-chart": {
      const { chart } = props;
      return (
        <Plot
          {...chart}
          style={{ width: "100%" }}
          config={{ displayModeBar: false }}
        />
      );
    }
    case "tooltip":
      const { content, placement } = props;
      return (
        <GooeyTooltip content={content} placement={placement}>
          <button>
            <RenderedChildren
              children={children}
              onChange={onChange}
              state={state}
            />
          </button>
        </GooeyTooltip>
      );
    case "popover": {
      const { content, placement, ...args } = props;
      return (
        <GooeyPopover
          content={content}
          children={children}
          onChange={onChange}
          state={state}
          placement={placement}
          {...args}
        />
      );
    }
    case "sidebar": {
      return (
        <GooeySidebar
          name={props.name}
          children={children}
          onChange={onChange}
          state={state}
          disabled={props.disabled}
          defaultOpen={props.defaultOpen}
          enableResize={props.enableResize}
        />
      );
    }
    default:
      return (
        <div>
          <pre>
            <code>{JSON.stringify(node)}</code>
          </pre>
        </div>
      );
  }
}

function ExecJs({
  src,
  args,
  state,
}: {
  src: string;
  args: Record<string, any>;
  state: Record<string, any>;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-new-func
    const fn = new Function(...Object.keys(args), src);
    fn(...Object.values(args));
  }, [src, args]);
  return null;
}

export function RenderedChildren({
  children,
  onChange,
  state,
  className,
}: {
  children: Array<TreeNode>;
  onChange: OnChange;
  state: Record<string, any>;
  className?: string;
}) {
  const location = useLocation();
  const routeKey = `${location.pathname}${location.search}`;
  let elements = children.map((node, idx) => {
    let key;
    if (node.props.name) {
      key = inputId(node.props);
    } else {
      key = `idx:${idx}`;
    }
    if (
      routeKey &&
      (node.name === "input" ||
        node.name === "textarea" ||
        node.name === "code-editor" ||
        node.name === "select")
    ) {
      key = `${routeKey}:${key}`;
    }
    let prevClassName = node.props.className || "";
    if (className && !prevClassName.includes(className)) {
      node.props.className = `${className} ${prevClassName}`;
    }
    return (
      <RenderedTreeNode
        key={key}
        node={node}
        onChange={onChange}
        state={state}
      />
    );
  });
  return <>{elements}</>;
}

function GooeySlider({
  className,
  id,
  props,
  state,
}: {
  className: string;
  id: string;
  props: Record<string, any>;
  state: Record<string, any>;
}) {
  const { label, name, type, help, tooltipPlacement, ...args } = props;
  const ref1 = useRef<HTMLInputElement>(null);
  const ref2 = useRef<HTMLInputElement>(null);

  // if server changed the value, update both inputs
  useEffect(() => {
    for (const element of [ref1.current, ref2.current]) {
      if (!element) continue;
      if (state && state[props.name] !== element.value) {
        element.value = state[props.name];
      }
    }
  }, [state, props.name]);
  return (
    <div className={className}>
      <InputLabel
        htmlFor={id}
        label={label}
        help={help}
        tooltipPlacement={tooltipPlacement}
      />
      <div className="d-flex justify-content-between align-items-center">
        <input
          ref={ref1}
          onChange={(e) => {
            if (ref2.current) ref2.current.value = e.target.value;
          }}
          type="number"
          {...args}
        />
        <input
          ref={ref2}
          onChange={(e) => {
            if (ref1.current) ref1.current.value = e.target.value;
          }}
          id={id}
          name={name}
          type={type}
          {...args}
        />
      </div>
    </div>
  );
}

export function GuiExpander({
  children,
  onChange,
  state,
  ...props
}: {
  onChange: () => void;
  children: ReactNode;
  state: Record<string, any>;
  [key: string]: any;
}) {
  const { open, name, label } = props;

  const ref = useRef<HTMLInputElement>(null);
  let isOpen = ref.current ? Boolean(ref.current.value) : open;

  useEffect(() => {
    if (!ref.current) return;
    if (open) {
      ref.current.value = "yes";
    } else if (ref.current.value && !state[name]) {
      onChange();
    }
  }, [state[name]]);

  return (
    <div className="gui-expander accordion">
      <input hidden ref={ref} name={name} />
      <div
        className={`gui-expander-header accordion-header accordion-button ${isOpen ? "" : "collapsed"
          }`}
        onClick={() => {
          if (!ref.current) return;
          ref.current.value = isOpen ? "" : "yes";
          onChange();
        }}
        {...props}
      >
        <RenderedMarkdown body={label} />
      </div>
      <div
        className="gui-expander-body"
        style={{ display: isOpen ? "block" : "none" }}
      >
        {children}
      </div>
    </div>
  );
}

function inputId(props: Record<string, any>) {
  return `input:${props.name}:${props.value}`;
}
