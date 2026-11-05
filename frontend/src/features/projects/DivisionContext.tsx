import * as React from "react";

import { readPref, writePref } from "@/lib/storage";

interface DivisionContextValue {
  /** Division chosen in the top bar; null = all divisions. Remembered per browser. */
  divisionId: string | null;
  setDivisionId: (id: string | null) => void;
}

const DivisionContext = React.createContext<DivisionContextValue>({ divisionId: null, setDivisionId: () => undefined });

export function DivisionProvider({ children }: { children: React.ReactNode }) {
  const [divisionId, setState] = React.useState<string | null>(() => readPref("division") || null);
  const value = React.useMemo(
    () => ({
      divisionId,
      setDivisionId: (id: string | null) => {
        writePref("division", id ?? "");
        setState(id);
      },
    }),
    [divisionId],
  );
  return <DivisionContext.Provider value={value}>{children}</DivisionContext.Provider>;
}

export function useCurrentDivision(): DivisionContextValue {
  return React.useContext(DivisionContext);
}
