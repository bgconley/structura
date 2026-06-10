import type {DocumentSummary} from "../types";

export function PipelineSummary({
  documents,
  total,
  previewed,
}: {
  documents: DocumentSummary[];
  total: number;
  previewed: number;
}) {
  // Only stages with real counts in the document-list payload are shown;
  // parse/extraction/indexing progress is not fabricated here.
  const needsReview = documents.filter((document) => document.reviewStatus === "needs_review").length;
  const reviewed = documents.filter(
    (document) => document.reviewStatus === "user_confirmed" || document.reviewStatus === "user_corrected",
  ).length;
  const stages: Array<[string, number, number, string]> = [
    ["Ingest", total, total, "green"],
    ["Preview", previewed, total, previewed === total ? "green" : "amber"],
    ["Needs review", needsReview, total, needsReview ? "amber" : "green"],
    ["Human reviewed", reviewed, total, "blue"],
  ];
  return (
    <section className="pipeline-panel">
      <div className="panel-title">
        <h2>Pipeline & Review Summary</h2>
      </div>
      <div className="stage-row">
        {stages.map(([label, done, count, tone]) => (
          <article className={`stage-card ${tone}`} key={label}>
            <span />
            <strong>{label}</strong>
            <small>{done} / {count}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
