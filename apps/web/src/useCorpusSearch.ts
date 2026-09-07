import {useRef, useState} from "react";
import {routeUrl, type AppRoute} from "./appRoutes";
import {createSavedSearch, runSearch} from "./searchApi";
import {defaultSearchFilterState, searchRequestFromFilters, type SearchFilterState} from "./searchFilters";
import {useKeyedRequest} from "./useKeyedRequest";
import type {SearchRequest} from "./types";

type SearchRoute = Extract<AppRoute, {view: "search"}>;
export function useCorpusSearch(route: SearchRoute | null, visit: string) {
  const routeIdentity = route ? `${visit}:${routeUrl(route)}` : "";
  const lifetime = useRef({routeIdentity, generation: 0});
  if (lifetime.current.routeIdentity !== routeIdentity) {
    lifetime.current = {routeIdentity, generation: lifetime.current.generation + 1};
  }
  const identity = `${routeIdentity}:${lifetime.current.generation}`;
  const [draft, setDraft] = useState<{identity: string; query: string; filters: SearchFilterState} | null>(null);
  const [notice, setNotice] = useState<{identity: string; text: string} | null>(null);
  const current = useRef(identity);
  current.current = identity;
  const query = draft?.identity === identity ? draft.query : route?.query ?? "";
  const filters = draft?.identity === identity ? draft.filters : route?.filters ?? defaultSearchFilterState;
  const request = useKeyedRequest(route?.submitted && route.query.trim() ? identity : null,
    (signal) => runSearch(searchRequestFromFilters(route!.query, route!.filters), signal));

  async function save(payload: SearchRequest) {
    const owner = identity;
    if (!payload.query.trim()) {
      setNotice({identity: owner, text: "Enter a search query before saving."});
      return;
    }
    try {
      const {query: queryText, includeDebug: _debug, limit: _limit, ...savedFilters} = payload;
      const saved = await createSavedSearch({name: `Search: ${queryText.trim().slice(0, 72)}`,
        queryText: queryText.trim(), filters: savedFilters});
      if (current.current === owner) setNotice({identity: owner, text: `Saved search: ${saved.name}`});
    } catch (error) {
      if (current.current === owner) setNotice({identity: owner,
        text: error instanceof Error ? error.message : "Unable to save search."});
    }
  }
  return {...request, query, filters, setQuery: (value: string) => setDraft({identity, query: value, filters}),
    setFilters: (value: SearchFilterState) => setDraft({identity, query, filters: value}),
    submitted: request.data && route ? {query: route.query, filters: route.filters} : null,
    status: notice?.identity === identity ? notice.text : null, save};
}
