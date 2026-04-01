import React, { useEffect, useRef, useState } from "react";
import { loadEventHandlers } from "./gooeyInput";

export function useJsonFormInput<T>({
  defaultValue,
  name,
  state,
  args,
  encode = JSON.stringify,
}: {
  defaultValue: T;
  name: string;
  state?: Record<string, any>;
  args?: Record<string, any>;
  encode?: (value: T) => string;
}): [React.FunctionComponent, T, (value: T) => void] {
  const [value, setValue] = useState(defaultValue);
  const ref = useRef<HTMLInputElement>(null);
  loadEventHandlers(value, setValue, args);

  // if the state value is changed by the server code, then update the value
  useEffect(() => {
    if (state && encode(state[name]) !== encode(value)) {
      setValue(state[name]);
    }
  }, [state, name]);

  return [
    () => <input hidden ref={ref} name={name} value={encode(value)} readOnly />,
    value,
    (value: T) => {
      if (ref.current) {
        ref.current.value = value === undefined ? "" : encode(value);
      }
      setValue(value);
    },
  ];
}
