import type {DocumentBrowseCounts} from "../types";
import {inboxStates, type InboxState} from "../documentBrowse";

export function InboxMetrics({
  counts,
  activeFilter,
  setActiveFilter,
}: {
  counts: DocumentBrowseCounts | null;
  activeFilter: InboxState;
  setActiveFilter: (filter: InboxState) => void;
}) {
  const selectedState = inboxStates.find((state) => state.value === activeFilter)!;
  return (
    <>
      <div className="metrics-row">
        <Metric label="Needs Review" value={counts?.needsReview} detail="Review required" tone="amber" />
        <Metric label="Unfiled Documents" value={counts?.unfiled} detail="Awaiting filing" tone="blue" />
        <Metric label="Awaiting Classification" value={counts?.awaitingClassification} detail="No recorded family decision" tone="blue" />
        <Metric label="Matching Documents" value={counts?.all} detail="Before the selected state" tone="blue" />
      </div>
      <div className="filter-row" aria-label="Document filters">
        {inboxStates.map((filter) => (
          <button
            key={filter.value}
            id={`inbox-state-${filter.value}`}
            className={filter.value === activeFilter ? "selected" : undefined}
            aria-pressed={filter.value === activeFilter}
            title={filter.detail}
            type="button"
            onClick={() => setActiveFilter(filter.value)}
          >
            <span aria-hidden="true" />
            {filter.label} <small className="filter-count">{counts?.[filter.count] ?? "—"}</small>
          </button>
        ))}
      </div>
      {activeFilter !== "all" ? <p className="inbox-filter-context"><strong>{selectedState.label}:</strong> {selectedState.detail}</p> : null}
      <p className="inbox-filter-context">Counts cover your query and folder before the selected state; a document can appear in several states.</p>
    </>
  );
}

function Metric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number | undefined;
  detail: string;
  tone: "blue" | "amber";
}) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong className={tone}>{value ?? "—"}</strong>
      <small>{detail}</small>
    </article>
  );
}
