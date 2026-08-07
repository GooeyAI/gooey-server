import { useEffect, useRef } from "react";
import type {
  CSSObjectWithLabel,
  MultiValueGenericProps,
  OptionProps,
  SingleValueProps,
  PlaceholderProps,
  MenuProps,
} from "react-select";
import Select, { components } from "react-select";
import { InputLabel } from "~/gooeyInput";
import { useJsonFormInput } from "~/jsonFormInput";
import { ClientOnlySuspense } from "~/lazyImports";
import { RenderedMarkdown } from "~/renderedMarkdown";

export default function GooeySelect({
  props,
  onChange,
  state,
}: {
  props: Record<string, any>;
  onChange: () => void;
  state: Record<string, any>;
}) {
  let { defaultValue, name, label, styles, help, tooltipPlacement, ...args } =
    props;
  let [JsonFormInput, value, setValue] = useJsonFormInput({
    defaultValue,
    name,
    state,
    args,
  });

  let onSelectChange = (newValue: any) => {
    if (newValue === undefined) return;
    if (!newValue) {
      setValue(newValue);
    } else if (args.isMulti) {
      setValue(newValue.map((opt: any) => opt.value));
    } else {
      setValue(newValue.value);
    }
    onChange();
  };

  let selectValue = args.options.filter((opt: any) =>
    args.isMulti ? value.includes(opt.value) : opt.value === value
  );
  // if selectedValue is not in options, then set it to the first option
  useEffect(() => {
    if (!selectValue.length && !args.allow_none) {
      setValue(args.isMulti ? [args.options[0].value] : args.options[0].value);
    }
  }, [args.isMulti, args.options, selectValue, setValue]);

  styles = {
    ...styles,
    menu: {
      width: "max-content",
      minWidth: "100%",
      maxWidth: "80vw",
      zIndex: 9999,
      ...styles?.menu,
    },
  };

  return (
    <div className={`gui-input gui-input-select ${args.className ?? ""}`}>
      <InputLabel
        label={label}
        help={help}
        tooltipPlacement={tooltipPlacement}
      />
      <JsonFormInput />
      <ClientOnlySuspense
        fallback={
          <select
            style={{ height: "38px", maxWidth: "90%", border: "none" }}
            className="d-flex align-items-center"
            disabled
          >
            {selectValue && (
              <option>
                <RenderedMarkdown
                  body={selectValue.map((it: any) => it.label).join(" | ")}
                  className="container-margin-reset"
                />
              </option>
            )}
            {args.options.map((opt: any) => (
              <option key={opt.value}>
                <RenderedMarkdown
                  body={opt.label}
                  className="container-margin-reset"
                />
              </option>
            ))}
          </select>
        }
      >
        {() => (
          <Select
            value={selectValue[0]?.value ? selectValue : null}
            onChange={onSelectChange}
            components={{
              Option,
              SingleValue,
              MultiValueLabel,
              Placeholder,
              Menu,
            }}
            // The menu is rendered on `body` rather than beside the control, because the
            // control is not always somewhere a menu can escape from: layout v2 puts its
            // forms inside a scrolling config pane nested in a pane with `overflow: hidden`,
            // and an inline menu is clipped by the first of those it grows past. A portal has
            // no clipping ancestor to hit. `menuPosition: fixed` goes with it - the portal is
            // placed against the viewport, so the menu must be measured the same way.
            menuPortalTarget={
              typeof document !== "undefined" ? document.body : undefined
            }
            menuPosition="fixed"
            // A portaled menu is positioned when it opens and does not follow a scroll
            // container moving underneath it, so it closes instead of floating away from its
            // control. Scrolling the menu's own list is exempt - that is not the page moving.
            closeMenuOnScroll={(e: Event) =>
              !(e.target instanceof Element) ||
              !e.target.closest("." + MENU_CLASS)
            }
            styles={{
              // above Bootstrap's modal (1055) - a select inside a dialog is common, and the
              // portal puts this at the end of `body` either way
              menuPortal: (base: CSSObjectWithLabel) => ({
                ...base,
                zIndex: 9999,
              }),
              // caller styles last, so a call site can still override the defaults above
              ...Object.fromEntries(
                Object.entries(styles ?? {}).map(([key, style]) => {
                  if (!style) return [key, undefined];
                  return [
                    key,
                    (base: CSSObjectWithLabel) => ({ ...base, ...style }),
                  ];
                })
              ),
            }}
            placeholder={selectValue[0]?.label}
            {...args}
          />
        )}
      </ClientOnlySuspense>
    </div>
  );
}

/* A stable hook on the menu. react-select's own class is an emotion hash (`css-xxxx-menu`),
   and matching that by substring also catches unrelated things like `account-menu-icon`. */
const MENU_CLASS = "gooey-select-menu";

const Menu = (props: MenuProps) => {
  const menuRef = useRef<HTMLDivElement>(null);

  /* Keep the menu inside the viewport.
   *
   * A menu is only as wide as its control by default, but a call site can widen it, and then
   * neither edge is safe: this used to right-align an overflowing menu to its control, which
   * on a narrow screen just moved the overflow to the other side - a 300px menu on a control
   * ending at x=224 landed at x=-76, cut off at the start of every option. Clamped to the
   * viewport instead, and capped so a menu wider than the screen cannot happen at all. */
  useEffect(() => {
    const menu = menuRef.current;
    if (!menu || !props.selectProps.menuIsOpen) return;
    const margin = 8;
    // cleared first, so reopening measures the menu's natural position rather than the one
    // the previous pass nudged it to
    menu.style.left = "";
    menu.style.right = "";
    menu.style.maxWidth = `${window.innerWidth - margin * 2}px`;
    const rect = menu.getBoundingClientRect();
    let shift = 0;
    if (rect.right > window.innerWidth - margin) {
      shift = window.innerWidth - margin - rect.right;
    }
    if (rect.left + shift < margin) {
      shift = margin - rect.left;
    }
    if (shift) menu.style.left = `${shift}px`;
  }, [props.selectProps.menuIsOpen]);

  return (
    <components.Menu {...props} innerRef={menuRef} className={MENU_CLASS}>
      {props.children}
    </components.Menu>
  );
};

const Option = (props: OptionProps) => (
  <components.Option
    {...props}
    children={
      <RenderedMarkdown body={props.label} className="container-margin-reset" />
    }
  />
);

const SingleValue = ({ children, ...props }: SingleValueProps) => (
  <components.SingleValue {...props}>
    {children ? (
      <RenderedMarkdown
        body={children.toString()}
        className="container-margin-reset"
      />
    ) : null}
  </components.SingleValue>
);

const MultiValueLabel = ({
  children,
  ...props
}: MultiValueGenericProps<any>) => (
  <components.MultiValueLabel {...props}>
    {children ? (
      <RenderedMarkdown
        body={children.toString()}
        className="container-margin-reset"
      />
    ) : null}
  </components.MultiValueLabel>
);

const Placeholder = (props: PlaceholderProps) => {
  if (props.children) {
    props = {
      ...props,
      children: (
        <RenderedMarkdown
          body={props.children.toString()}
          className="container-margin-reset"
        />
      ),
    };
  }
  return <components.Placeholder {...props} />;
};
