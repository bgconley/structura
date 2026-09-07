import {useEffect, useRef, useState} from "react";

// Only the latest request for the currently rendered identity may publish data.
// A changed key hides old data synchronously, before effect cleanup runs.
export function useKeyedRequest<T>(key: string | null, load: (signal: AbortSignal) => Promise<T>) {
  type State = {generation: number; key: string; data: T | null; error: Error | null; loading: boolean};
  const [state, setState] = useState<State | null>(null);
  const current = useRef({key, load, generation: 0});
  current.current = {key, load, generation: current.current.generation + (key !== current.current.key ? 1 : 0)};
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);

  async function reload(): Promise<void> {
    const requestedKey = current.current.key;
    if (!requestedKey) return;
    const generation = current.current.generation;
    const request = ++sequence.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setState((old) => ({generation, key: requestedKey, data: old?.key === requestedKey && old.generation === generation ? old.data : null,
      loading: true, error: null}));
    const owns = () => !abort.signal.aborted && request === sequence.current
      && current.current.key === requestedKey && current.current.generation === generation;
    try {
      const data = await current.current.load(abort.signal);
      if (owns()) setState({generation, key: requestedKey, data, loading: false, error: null});
    } catch (error) {
      if (owns()) setState({generation, key: requestedKey, data: null, loading: false,
        error: error instanceof Error ? error : new Error("Unable to load this page.")});
    }
  }

  useEffect(() => {
    if (key) void reload();
    return () => { sequence.current += 1; controller.current?.abort(); };
  }, [key]);

  const matching = state?.key === key && state.generation === current.current.generation ? state : null;
  return {data: matching?.data ?? null, error: matching?.error ?? null,
    loading: !!key && (matching?.loading ?? true), reload};
}
