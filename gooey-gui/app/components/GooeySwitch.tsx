import { InputLabel, useGooeyCheckedInput } from "~/gooeyInput";

const GooeySwitch = ({
  props,
  state,
}: {
  props: Record<string, any>;
  state: Record<string, any>;
}) => {
  const {
    label,
    name,
    defaultChecked,
    className = "",
    size = "large",
    help,
    tooltipPlacement,
    ...args
  } = props;
  const inputRef = useGooeyCheckedInput({
    stateChecked: state[name],
    defaultChecked,
  });
  return (
    <div
      className={
        "d-flex justify-content-between align-items-center container-margin-reset py-2 gooey-switch-container " +
        className
      }
    >
      <InputLabel
        label={label}
        help={help}
        tooltipPlacement={tooltipPlacement}
      />
      <div>
        <input
          hidden
          ref={inputRef}
          id={name}
          name={name}
          defaultChecked={defaultChecked}
          className={`gooey-switch gooey-switch--shadow--${size}`}
          {...args}
          type="checkbox"
        />
        <label htmlFor={name} />
      </div>
    </div>
  );
};

export default GooeySwitch;
