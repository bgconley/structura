import {useEffect, useRef, useState} from "react";
import {getLineHistory} from "./api";
import type {HistorySelector, LineHistoryEntry} from "./types";

export function useLineItemHistory(documentId: string, selector: HistorySelector, revision: string) {
  const key = JSON.stringify([documentId, selector, revision]);
  const [state, setState] = useState<{key: string; items: LineHistoryEntry[]; cursor: string | null; loading: boolean; error: string | null}>
    ({key, items: [], cursor: null, loading: true, error: null});
  const sequence = useRef(0), latest = useRef(key), pending = useRef(false);
  latest.current = key;
  useEffect(() => { pending.current = false; void load(); return () => { sequence.current++; }; }, [key]);
  async function load(cursor?: string) {
    if (pending.current) return;
    const attempt = ++sequence.current;
    pending.current = true;
    setState((previous) => ({key, items: cursor && previous.key === key ? previous.items : [], cursor: cursor ?? null, loading: true, error: null}));
    try {
      const response = await getLineHistory(documentId, selector, cursor);
      if (attempt !== sequence.current || key !== latest.current) return;
      setState((previous) => ({key, items: [...(cursor ? previous.items : []), ...response.items]
        .filter((entry, index, items) => items.findIndex((item) => item.id === entry.id) === index),
      cursor: response.nextCursor, loading: false, error: null}));
    } catch (failure) {
      if (attempt === sequence.current && key === latest.current) setState({key, items: [], cursor: null, loading: false,
        error: failure instanceof Error ? failure.message : "Line history could not be loaded."});
    } finally { if (attempt === sequence.current) pending.current = false; }
  }
  return {items: state.key === key ? state.items : [], loading: state.key !== key || state.loading,
    error: state.key === key ? state.error : null, cursor: state.key === key ? state.cursor : null,
    more: () => load(state.cursor ?? undefined), reload: () => load()};
}
