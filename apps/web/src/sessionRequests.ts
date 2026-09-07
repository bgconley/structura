// A browser session owns its requests. Rotation aborts requests and rejects late
// responses before a previous login can publish data or expire a newer login.
let lifetime = new AbortController();
let onUnauthorized: (() => void) | undefined;

export function rotateSessionRequests(): void {
  lifetime.abort();
  lifetime = new AbortController();
}

export function listenForUnauthorized(listener: () => void): () => void {
  onUnauthorized = listener;
  return () => {
    if (onUnauthorized === listener) onUnauthorized = undefined;
  };
}

export function sessionRequestScope(signal?: AbortSignal | null) {
  const owner = lifetime;
  return {
    signal: signal ? AbortSignal.any([owner.signal, signal]) : owner.signal,
    assertCurrent() {
      owner.signal.throwIfAborted();
      signal?.throwIfAborted();
    },
    unauthorized() {
      if (owner === lifetime && !owner.signal.aborted) onUnauthorized?.();
    },
  };
}
