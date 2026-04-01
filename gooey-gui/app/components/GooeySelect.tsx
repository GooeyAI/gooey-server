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
            styles={{
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

const Menu = (props: MenuProps) => {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuRef.current) return;
    let rect = menuRef.current.getBoundingClientRect();
    let overflowRight = rect.right > window.innerWidth - 25;
    if (overflowRight) {
      menuRef.current.style.right = "0";
    }
  }, [menuRef, props.selectProps.menuIsOpen]);

  return (
    <components.Menu {...props} innerRef={menuRef}>
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
