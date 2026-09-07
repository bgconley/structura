import {useCallback, useEffect, useRef, useState} from "react";

import {ApiError, configureSecurityCookieNames, csrfToken, fetchJson} from "./api";
import {listenForUnauthorized, rotateSessionRequests} from "./sessionRequests";
import type {SessionInfo} from "./types";

type Phase = "checking" | "anonymous" | "authenticated" | "signing-out" | "sign-out-failed" | "unavailable";
type SessionState = {
  phase: Phase;
  session: SessionInfo | null;
  error: string | null;
  message: string | null;
  submitting: boolean;
  generation: number;
};
export type PasswordCredentials = {email: string; password: string};
const INITIAL: SessionState = {phase: "checking", session: null, error: null,
  message: null, submitting: false, generation: 0};
const EXPIRED = "Your session has ended. Sign in again to continue.";

function sessionIdentity(session: SessionInfo | null): string {
  return [session?.sessionId, session?.userId, session?.householdId, session?.email].join(":");
}

export function useSession() {
  const [state, setState] = useState(INITIAL);
  const current = useRef(state);
  const sequence = useRef(0);
  const checking = useRef(false);
  const channel = useRef<BroadcastChannel | null>(null);
  const update = useCallback((next: SessionState) => {
    current.current = next;
    setState(next);
  }, []);

  const clear = useCallback((message: string | null) => {
    sequence.current += 1;
    checking.current = false;
    rotateSessionRequests();
    configureSecurityCookieNames({});
    update({...INITIAL, phase: "anonymous", message, generation: current.current.generation + 1});
  }, [update]);

  const adopt = useCallback((session: SessionInfo) => {
    const expires = Date.parse(session.expiresAt ?? "");
    if (!session.isAuthenticated || (Number.isFinite(expires) && expires <= Date.now())) {
      clear(EXPIRED);
      return;
    }
    const changed = current.current.phase !== "authenticated"
      || sessionIdentity(session) !== sessionIdentity(current.current.session);
    if (changed) rotateSessionRequests();
    configureSecurityCookieNames(session);
    update({...INITIAL, phase: "authenticated", session,
      generation: current.current.generation + (changed ? 1 : 0)});
  }, [clear, update]);

  const check = useCallback(async () => {
    if (checking.current || current.current.submitting
      || ["signing-out", "sign-out-failed"].includes(current.current.phase)) return;
    checking.current = true;
    const request = sequence.current;
    try {
      const session = await fetchJson<SessionInfo>("/api/v1/auth/session");
      if (request === sequence.current) adopt(session);
    } catch (error) {
      if (request !== sequence.current) return;
      if (error instanceof ApiError && error.status === 401) {
        clear(current.current.phase === "authenticated" ? EXPIRED : null);
      } else if (!(error instanceof DOMException && error.name === "AbortError")) {
        update({...current.current,
          phase: current.current.session ? "authenticated" : "unavailable",
          error: "Unable to check your session. Check the connection and try again."});
      }
    } finally {
      if (request === sequence.current) checking.current = false;
    }
  }, [adopt, clear, update]);

  useEffect(() => {
    // StrictMode can remount effects; invalidate the first bootstrap's response.
    checking.current = false;
    const unsubscribe = listenForUnauthorized(() => clear(EXPIRED));
    void check();
    const onForeground = () => {
      if (document.visibilityState === "visible" && current.current.phase === "authenticated") void check();
    };
    window.addEventListener("focus", onForeground);
    document.addEventListener("visibilitychange", onForeground);
    const interval = window.setInterval(onForeground, 60_000);
    if (typeof BroadcastChannel !== "undefined") {
      const connection = new BroadcastChannel("structura-session");
      channel.current = connection;
      connection.onmessage = (event: MessageEvent) => {
        if (event.data?.type === "signed-out"
          && event.data?.identity === sessionIdentity(current.current.session)) clear(EXPIRED);
        if (event.data?.type === "signed-in"
          && !["signing-out", "sign-out-failed"].includes(current.current.phase)) {
          // Cookies are shared across tabs. Drop the previous account's state
          // before reloading under the newly installed session cookie.
          sequence.current += 1;
          checking.current = false;
          rotateSessionRequests();
          configureSecurityCookieNames({});
          update({...INITIAL, generation: current.current.generation + 1});
          void check();
        }
      };
    }
    return () => {
      sequence.current += 1;
      rotateSessionRequests();
      unsubscribe();
      window.clearInterval(interval);
      window.removeEventListener("focus", onForeground);
      document.removeEventListener("visibilitychange", onForeground);
      channel.current?.close();
    };
  }, [check, clear, update]);

  useEffect(() => {
    const expires = Date.parse(state.session?.expiresAt ?? "");
    if (state.phase !== "authenticated" || !Number.isFinite(expires)) return;
    let cancelled = false;
    let timer: number;
    const schedule = () => {
      timer = window.setTimeout(() => {
        if (cancelled) return;
        if (expires <= Date.now()) clear(EXPIRED);
        else {
          // Long sessions exceed the browser's timeout range. Re-arm even
          // when the session check fails or returns the same absolute expiry.
          schedule();
          void check();
        }
      }, Math.max(0, Math.min(expires - Date.now(), 2_147_483_647)));
    };
    schedule();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [state.phase, state.session?.expiresAt, check, clear]);

  async function signIn(credentials: PasswordCredentials) {
    if (current.current.submitting) return;
    const request = ++sequence.current;
    checking.current = false;
    rotateSessionRequests();
    update({...current.current, submitting: true, error: null});
    try {
      // Another tab may have installed a session after this tab showed login.
      // Discover its cookie configuration without adopting that account or
      // discarding the credentials the user is currently submitting.
      try {
        const existing = await fetchJson<SessionInfo>("/api/v1/auth/session");
        if (request !== sequence.current) return;
        configureSecurityCookieNames(existing);
      } catch (error) {
        if (request !== sequence.current) return;
        if (!(error instanceof ApiError && error.status === 401)) throw error;
      }
      if (request !== sequence.current) return;
      const session = await fetchJson<SessionInfo>("/api/v1/auth/session", {
        method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken()},
        body: JSON.stringify({method: "password", ...credentials}),
      });
      if (request === sequence.current) {
        adopt(session);
        if (current.current.phase === "authenticated") {
          channel.current?.postMessage({type: "signed-in", identity: sessionIdentity(session)});
        }
      }
    } catch (error) {
      if (request === sequence.current) update({...current.current, submitting: false,
        error: error instanceof Error ? error.message : "Sign-in failed."});
    }
  }

  async function signOut() {
    if (current.current.phase === "signing-out") return;
    const identity = sessionIdentity(current.current.session);
    const request = ++sequence.current;
    checking.current = false;
    // Hide and unmount all private views while revocation is being confirmed.
    rotateSessionRequests();
    update({...current.current, phase: "signing-out", error: null});
    try {
      await fetchJson<void>("/api/v1/auth/session", {
        method: "DELETE", headers: {"X-CSRF-Token": csrfToken()},
      });
    } catch (error) {
      if (request !== sequence.current) return;
      if (!(error instanceof ApiError && error.status === 401)) {
        update({...current.current, phase: "sign-out-failed",
          error: "Sign-out could not be confirmed. Your documents are hidden. Try signing out again."});
        return;
      }
    }
    if (request === sequence.current) {
      channel.current?.postMessage({type: "signed-out", identity});
      clear("You have signed out.");
    }
  }

  return {...state, signIn, signOut, retry: check};
}
