import {useEffect, useRef, useState} from "react";
import {parseAppRoute, routeUrl, type AppRoute} from "./appRoutes";
import type {EvidenceTarget} from "./types";

type Entry = {key: string; index: number; scroll: number; focusId?: string; returnIndex?: number};
function currentEntry(): Entry {
  const entry = window.history.state?.structura;
  if (entry && typeof entry.key === "string" && Number.isFinite(entry.scroll) && Number.isSafeInteger(entry.index)
    && (entry.focusId === undefined || typeof entry.focusId === "string")) return entry;
  const next = {key: crypto.randomUUID(), index: 0, scroll: 0};
  window.history.replaceState({structura: next}, "");
  return next;
}

export function useAppNavigation() {
  const [location, setLocation] = useState(() => ({route: parseAppRoute(window.location.pathname + window.location.search),
    entry: currentEntry(), motion: "initial"}));
  const evidence = useRef(new Map<string, EvidenceTarget>());
  const restored = useRef<typeof location | null>(null);
  const latest = useRef(location);
  latest.current = location;
  useEffect(() => {
    const changed = () => setLocation({route: parseAppRoute(window.location.pathname + window.location.search),
      entry: currentEntry(), motion: "pop"});
    window.addEventListener("popstate", changed);
    return () => window.removeEventListener("popstate", changed);
  }, []);

  function navigate(route: AppRoute, options: {replace?: boolean; evidence?: EvidenceTarget} = {}) {
    const active = document.activeElement;
    const previous = {...latest.current.entry, scroll: window.scrollY,
      focusId: active instanceof HTMLElement ? active.id : undefined};
    window.history.replaceState({structura: previous}, "");
    const entry = options.replace ? previous : {key: crypto.randomUUID(), index: previous.index + 1, scroll: 0,
      returnIndex: route.view === "viewer"
        ? latest.current.route.view === "viewer" ? previous.returnIndex : previous.index : undefined};
    window.history[options.replace ? "replaceState" : "pushState"]({structura: entry}, "", routeUrl(route));
    if (options.evidence) evidence.current.set(entry.key, options.evidence);
    else if (!options.replace) evidence.current.delete(entry.key);
    setLocation({route, entry, motion: options.replace ? "replace" : "push"});
  }

  function restore(ready: boolean) {
    if (!ready || restored.current === latest.current) return;
    restored.current = latest.current;
    if (latest.current.motion === "replace") return;
    const {entry, motion} = latest.current;
    const target = motion === "pop" && entry.focusId ? document.getElementById(entry.focusId) : null;
    (target ?? document.getElementById("route-content"))?.focus({preventScroll: true});
    window.scrollTo({top: motion === "pop" ? entry.scroll : 0});
  }

  function returnTo(route: AppRoute) {
    const {entry} = latest.current;
    if (entry.returnIndex !== undefined && entry.returnIndex < entry.index) {
      window.history.go(entry.returnIndex - entry.index);
    } else navigate(route);
  }

  return {...location, navigate, returnTo, restore, evidenceTarget: evidence.current.get(location.entry.key) ?? null};
}
