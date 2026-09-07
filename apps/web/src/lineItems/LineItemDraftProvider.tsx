import {createContext, useContext, useEffect, useRef, useState, type ReactNode} from "react";
import type {LineRequest} from "./types";

export type LineDraft = {actor: string; documentId: string; sourceId: string | null; comment: string;
  request: LineRequest | null; phase: "editing" | "reviewing" | "saving" | "conflict" | "unknown" | "saved";
  message: string | null};
type DraftStore = {actor: string; authorized: boolean; entries: Map<string, LineDraft>;
  update: (key: string, value: LineDraft) => void; removeDocument: (documentId: string) => void};
const Context = createContext<DraftStore | null>(null);

// Owned by the authenticated shell: no storage, history.state, or cross-account reuse.
export function LineItemDraftProvider({actor, authorized, children}: {actor: string; authorized: boolean; children: ReactNode}) {
  const [entries, setEntries] = useState(() => new Map<string, LineDraft>());
  const retained = useRef(entries);
  retained.current = entries;
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; retained.current.clear(); }; }, []);
  const update = (key: string, value: LineDraft) => {
    if (live.current && value.actor === actor) setEntries((previous) => new Map(previous).set(key, value));
  };
  return <Context.Provider value={{actor, authorized, entries, update, removeDocument: (documentId) => {
    if (live.current) setEntries((previous) => new Map([...previous].filter(([, draft]) => draft.documentId !== documentId)));
  }}}>{children}</Context.Provider>;
}
export function useLineDrafts() {
  const store = useContext(Context);
  if (!store) throw new Error("Line review requires an authenticated session.");
  return store;
}
