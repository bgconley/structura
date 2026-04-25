import type {DocumentSummary} from "../types";

const filterLabels = [
  "All",
  "Needs Review",
  "Unfiled",
  "Awaiting Classification",
  "Duplicates",
  "Low Confidence",
  "Extracted",
  "Indexed",
];

export function InboxMetrics({
  documents,
  total,
  activeFilter,
  setActiveFilter,
}: {
  documents: DocumentSummary[];
  total: number;
  activeFilter: string;
  setActiveFilter: (filter: string) => void;
}) {
  const needsReview = documents.filter((document) => document.reviewStatus === "needs_review").length;
  const unfiled = documents.filter((document) => !(document.folderPaths?.length)).length;

  return (
    <>
      <div className="metrics-row">
        <Metric label="Needs Review" value={needsReview} detail="Review required" tone="amber" />
        <Metric label="Unfiled Documents" value={unfiled} detail="Awaiting filing" tone="blue" />
        <Metric label="Awaiting Classification" value={total} detail="Phase 3 ready" tone="blue" />
        <Metric label="Missing Required Fields" value={0} detail="Needs attention" tone="amber" />
        <Metric label="Duplicate Suspects" value={0} detail="Exact hash flagged" tone="amber" />
        <Metric label="Recent Uploads" value={total} detail="Visible in inbox" tone="blue" />
      </div>
      <div className="filter-row" aria-label="Document filters">
        {filterLabels.map((filter) => (
          <button
            key={filter}
            className={filter === activeFilter ? "selected" : undefined}
            type="button"
            onClick={() => setActiveFilter(filter)}
          >
            <span />
            {filter}
          </button>
        ))}
      </div>
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
  value: number;
  detail: string;
  tone: "blue" | "amber";
}) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong className={tone}>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}
