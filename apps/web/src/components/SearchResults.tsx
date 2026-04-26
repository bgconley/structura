import {FormEvent, useState} from "react";

import {familyLabel, formatAmount, formatDate} from "../format";
import type {EvidenceTarget, Folder, SearchRequest, SearchResponse, SearchResult, Tag} from "../types";
import {
  activeSearchFilters,
  defaultSearchFilterState,
  SearchFilterPanel,
  searchRequestFromFilters,
  selectedSearchFolder,
} from "./SearchFilterPanel";
import "./SearchResults.css";

export function SearchResults({
  query,
  setQuery,
  response,
  isLoading,
  error,
  status,
  folders,
  tags,
  onSubmit,
  onSaveSearch,
  onOpenDocument,
}: {
  query: string;
  setQuery: (query: string) => void;
  response: SearchResponse | null;
  isLoading: boolean;
  error: string | null;
  status: string | null;
  folders: Folder[];
  tags: Tag[];
  onSubmit: (payload: SearchRequest) => Promise<void>;
  onSaveSearch: (payload: SearchRequest) => Promise<void>;
  onOpenDocument: (documentId: string, target?: EvidenceTarget) => void;
}) {
  const [filters, setFilters] = useState(defaultSearchFilterState);

  function requestPayload(): SearchRequest {
    return searchRequestFromFilters(query, filters);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit(requestPayload());
  }

  const items = response?.items ?? [];
  const selectedFolder = selectedSearchFolder(filters, folders);
  const activeFilters = activeSearchFilters(filters, folders);

  return (
    <section className="search-workbench">
      <div className="search-heading">
        <div>
          <h1>Corpus Search</h1>
          <p>Use native language to retrieve documents without turning the app into a chat surface.</p>
        </div>
      </div>
      <form className="search-query-card" onSubmit={(event) => void handleSubmit(event)}>
        <div>
          <label htmlFor="corpus-search-query">Ask Structura to find documents</label>
          <input
            id="corpus-search-query"
            aria-label="Corpus search query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find medical documents related to claim ABC123 where I may still owe money"
          />
        </div>
        <button type="submit" disabled={isLoading || !query.trim()}>
          {isLoading ? "Searching..." : "Search corpus"}
        </button>
        <div className="retrieval-chips" aria-label="Retrieval signals">
          <span>lexical</span>
          <span>semantic</span>
          <span>metadata</span>
          <span className="deferred">relationships</span>
        </div>
      </form>
      <div className="search-layout">
        <SearchFilterPanel
          filters={filters}
          folders={folders}
          tags={tags}
          onChange={setFilters}
        />
        <section className="search-results-panel">
          <div className="panel-title">
            <h2>Ranked Results</h2>
            <p>{items.length} result{items.length === 1 ? "" : "s"}</p>
          </div>
          {error ? <div className="inline-error">{error}</div> : null}
          {status ? <div className="search-status">{status}</div> : null}
          {!items.length && response ? (
            <div className="search-empty">
              <strong>No matching documents</strong>
              <span>
                Active filters: {activeFilters.length ? activeFilters.join(", ") : "none"}
              </span>
            </div>
          ) : null}
          <div className="search-result-list">
            {items.map((item, index) => (
              <SearchResultCard
                key={`${item.documentId}-${item.matchedChunkId ?? index}`}
                item={item}
                selected={index === 0}
                onOpenDocument={onOpenDocument}
              />
            ))}
          </div>
        </section>
        <aside className="retrieval-panel">
          <h2>Why these results</h2>
          <p>
            Structura translated the request into retrieval signals, then returned documents with
            citations. This is search assistance, not an open-ended chat session.
          </p>
          <h3>Query interpretation</h3>
          <div className="filter-chip-list explanation">
            <span>{query ? `query = ${query.slice(0, 42)}` : "query pending"}</span>
            <span>mode = {filters.mode}</span>
            {filters.family ? <span>document_family = {filters.family}</span> : null}
            {selectedFolder ? <span>folder = {selectedFolder.name}</span> : null}
            {filters.tag ? <span>tag = {filters.tag}</span> : null}
            {filters.reviewStatus ? <span>review_status = {filters.reviewStatus}</span> : null}
            {filters.sensitivity ? <span>sensitivity = {filters.sensitivity}</span> : null}
            {response?.debug?.filtersApplied !== undefined ? (
              <span>filters = {String(response.debug.filtersApplied)}</span>
            ) : null}
          </div>
          <h3>Top evidence sources</h3>
          <div className="evidence-source-list">
            {items.slice(0, 4).map((item) => (
              <button
                key={item.documentId}
                type="button"
                onClick={() => onOpenDocument(item.documentId, evidenceTargetFromResult(item))}
              >
                <span>{item.evidence?.[0]?.sourceText ?? item.snippet ?? item.title}</span>
                <em>go</em>
              </button>
            ))}
          </div>
          <h3>Facets</h3>
          <FacetBlock title="Families" values={response?.facets?.families} />
          <FacetBlock title="Folders" values={response?.facets?.folders} />
          <FacetBlock title="Tags" values={response?.facets?.tags} />
          <FacetBlock title="Review status" values={response?.facets?.reviewStatus} />
          <FacetBlock title="Sensitivity" values={response?.facets?.sensitivity} />
          <FacetBlock title="Date buckets" values={response?.facets?.dateBuckets} />
          <div className="retrieval-actions">
            <button
              type="button"
              onClick={() => void onSaveSearch(requestPayload())}
            >
              Save search
            </button>
            <button type="button" className="primary">Create review set</button>
          </div>
        </aside>
      </div>
    </section>
  );
}

function SearchResultCard({
  item,
  selected,
  onOpenDocument,
}: {
  item: SearchResult;
  selected: boolean;
  onOpenDocument: (documentId: string, target?: EvidenceTarget) => void;
}) {
  return (
    <article className={`search-result-card ${selected ? "selected" : ""}`}>
      <button type="button" onClick={() => onOpenDocument(item.documentId)}>
        <span className="search-thumb" />
        <span>
          <strong>{item.title}</strong>
          <small>
            {item.counterpartyDisplay ?? familyLabel(item.family ?? "generic")}
            {item.amountTotal ? ` · ${formatAmount(item.amountTotal)}` : ""}
            {item.documentDate ? ` · ${formatDate(item.documentDate)}` : ""}
          </small>
          <em>{item.snippet ?? "Evidence-backed result available."}</em>
          <b>{item.explanation ?? "matched by search rank"}</b>
        </span>
      </button>
      <div className="result-actions">
        <span>{(item.score ?? 0) > 0.02 ? "High match" : "Medium match"}</span>
        <button
          type="button"
          onClick={() => onOpenDocument(item.documentId, evidenceTargetFromResult(item))}
        >
          Jump to evidence
        </button>
      </div>
    </article>
  );
}

function FacetBlock({title, values}: {title: string; values?: Record<string, number>}) {
  const entries = Object.entries(values ?? {}).slice(0, 6);
  return (
    <div className="facet-block">
      <strong>{title}</strong>
      {entries.length ? entries.map(([key, count]) => (
        <span key={key}>{key}: {count}</span>
      )) : <span>none</span>}
    </div>
  );
}

function evidenceTargetFromResult(item: SearchResult): EvidenceTarget {
  const evidence = item.evidence?.[0];
  return {
    documentId: item.documentId,
    pageNumber: evidence?.pageNumber ?? item.pageNumber,
    sourceText: evidence?.sourceText ?? item.snippet,
    bbox: evidence?.bbox,
    elementId: evidence?.elementId,
    tableId: evidence?.tableId,
    rowIndex: evidence?.rowIndex,
    textSpan: evidence?.textSpan,
  };
}
