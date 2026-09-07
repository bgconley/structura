import {useEffect, useRef} from "react";
import type {SessionInfo} from "../types";
import "./SessionMenu.css";

export function SessionMenu({session, onSignOut, error}: {
  session: SessionInfo;
  onSignOut: () => Promise<void>;
  error: string | null;
}) {
  const menu = useRef<HTMLDetailsElement>(null);
  const name = session.displayName?.trim() || session.email || "Signed-in user";
  const initials = name.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (menu.current && !menu.current.contains(event.target as Node)) menu.current.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  return (
    <details className="session-menu" ref={menu} onKeyDown={(event) => {
      if (event.key === "Escape" && menu.current?.open) {
        event.preventDefault();
        menu.current.open = false;
        menu.current.querySelector("summary")?.focus();
      }
    }}>
      <summary className="avatar" aria-label={`Account: ${name}`} title={name}>{initials}</summary>
      <div className="session-menu-panel">
        <strong>{name}</strong>
        {session.email ? <span>{session.email}</span> : null}
        {error ? <p role="status">{error}</p> : null}
        <button type="button" className="command-button" onClick={() => void onSignOut()}>Sign out</button>
      </div>
    </details>
  );
}
