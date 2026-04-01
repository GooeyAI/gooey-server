import { createContext, useContext, useEffect, useRef } from "react";

export type GlobalContextType = {
  session_state: Record<string, any>;
  update_session_state: (newState: Record<string, any>) => void;
  set_session_state: (newState: Record<string, any>) => void;
  rerun: () => void;
  navigate: (path: string) => void;
};

export const GlobalContext = createContext<{
  current: GlobalContextType;
}>({
  current: {
    session_state: {},
    update_session_state: () => {},
    set_session_state: () => {},
    rerun: () => {},
    navigate: () => {},
  },
});

export function GlobalContextProvider({
  value,
  children,
}: {
  value: GlobalContextType;
  children: React.ReactNode;
}) {
  const ctx = useRef(value);

  useEffect(() => {
    ctx.current = value;
  }, [value]);

  return (
    <GlobalContext.Provider value={ctx}>{children}</GlobalContext.Provider>
  );
}

export function useGlobalContext() {
  return useContext(GlobalContext);
}
