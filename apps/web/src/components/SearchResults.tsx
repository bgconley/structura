import {FormEvent, useState} from "react";

import {familyLabel, formatAmount, formatDate} from "../format";
import type {EvidenceTarget, SearchMode, SearchRequest, SearchResponse, SearchResult} from "../types";
import "./SearchResults.css";

const modeOptions: SearchMode[] = ["hybrid", "lexical", "semantic"];
const familyOptions = [
  "",
  "medical_eob",
  "medical_bill",
  "invoice",
  "receipt",
  "warranty",
  "tax_document",
  "legal_contract",
];

export function SearchResults({
  query,
  setQuery,
  response,
  isLoading,
  error,
  status,
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
  onSubmit: (payload: SearchRequest) => Promise<void>;
  onSaveSearch: (payload: SearchRequest) => Promise<void>;
  onOpenDocument: (documentId: string, target?: EvidenceTarget) => void;
}) {
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [family, setFamily] = useState("");
  const [reviewedOnly, setReviewedOnly] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({
      query,
      mode,
      families: family ? [family] : [],
      reviewedOnly: reviewedOnly || undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
      includeDebug: true,
    });
  }

  const items = response?.items ?? [];
  const activeFilters = [
    family ? familyLabel(family) : null,
    reviewedOnly ? "reviewed only" : null,
    dateFrom || dateTo ? `${dateFrom || "any"} to ${dateTo || "any"}` : null,
  ].filter((value): value is string => Boolean(value));

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
        <aside className="search-filter-panel">
          <h2>Filters</h2>
          <label>
            Search mode
            <select
              aria-label="Search mode"
              value={mode}
              onChange={(event) => setMode(event.target.value as SearchMode)}
            >
              {modeOptions.map((option) => <option key={option}>{option}</option>)}
            </select>
          </label>
          <label>
            Document family filter
            <select
              aria-label="Document family filter"
              value={family}
              onChange={(event) => setFamily(event.target.value)}
            >
              {familyOptions.map((option) => (
                <option key={option} value={option}>{option ? familyLabel(option) : "Any family"}</option>
              ))}
            </select>
          </label>
          <label>
            Date from
            <input value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} type="date" />
          </label>
          <label>
            Date to
            <input value={dateTo} onChange={(event) => setDateTo(event.target.value)} type="date" />
          </label>
          <label className="filter-check">
            <input
              checked={reviewedOnly}
              onChange={(event) => setReviewedOnly(event.target.checked)}
              type="checkbox"
            />
            Reviewed only
          </label>
          <div className="filter-chip-list">
            <span className={family ? "selected" : undefined}>
              Family: {family || "Any"}
            </span>
            <span>Date: {dateFrom || "any"} - {dateTo || "any"}</span>
            <span>Review: {reviewedOnly ? "Reviewed" : "Any"}</span>
          </div>
        </aside>
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
            <span>mode = {mode}</span>
            {family ? <span>document_family = {family}</span> : null}
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
          <FacetBlock title="Tags" values={response?.facets?.tags} />
          <div className="retrieval-actions">
            <button
              type="button"
              onClick={() => void onSaveSearch({
                query,
                mode,
                families: family ? [family] : [],
                reviewedOnly: reviewedOnly || undefined,
                dateFrom: dateFrom || undefined,
                dateTo: dateTo || undefined,
              })}
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
