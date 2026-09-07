import type {InboxRoute} from "./appRoutes";
import type {DocumentSort, InboxState} from "./documentBrowse";
import {useDocumentList} from "./useDocumentList";

export function useInboxBrowse(route: InboxRoute, navigate: (route: InboxRoute, options?: {replace?: boolean}) => void) {
  const list = useDocumentList(route);
  const offset = route.offset ?? 0, limit = route.limit ?? 50;
  const state = route.inboxState ?? "all", sort = route.sort ?? "uploaded_desc";
  function change(patch: Partial<InboxRoute>, replace = false) {
    navigate({...route, ...patch}, {replace});
  }
  return {list, route, offset, limit, state, sort,
    hasFilters: !!route.query?.trim() || !!route.folderId || state !== "all",
    select: (documentId: string) => change({documentId}, true),
    setQuery: (query: string) => change({query: query || undefined, offset: 0}, true),
    setState: (inboxState: InboxState) => change({inboxState, offset: 0}),
    setSort: (sort: DocumentSort) => change({sort, offset: 0}),
    setFolder: (folderId: string | null) => change({folderId: folderId ?? undefined, offset: 0}),
    setOffset: (offset: number) => change({offset}),
    setLimit: (limit: number) => change({limit, offset: 0}),
    clearFilters: () => change({query: undefined, folderId: undefined, inboxState: "all", offset: 0}),
  };
}

export type InboxBrowse = ReturnType<typeof useInboxBrowse>;
