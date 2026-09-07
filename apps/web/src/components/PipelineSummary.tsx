import type {DocumentBrowseCounts} from "../types";

export function PipelineSummary({
  counts,
}: {
  counts: DocumentBrowseCounts | null;
}) {
  const stages: Array<[string, number | undefined, string]> = [
    ["Registered", counts?.all, "blue"],
    ["Preview available", counts?.previewReady, "blue"],
    ["Needs review", counts?.needsReview, "amber"],
    ["Human reviewed", counts?.humanReviewed, "blue"],
  ];
  return (
    <section className="pipeline-panel">
      <div className="panel-title">
        <h2>Document Readiness</h2>
      </div>
      <div className="stage-row">
        {stages.map(([label, done, tone]) => (
          <article className={`stage-card ${tone}`} key={label}>
            <span />
            <strong>{label}</strong>
            <small>{done ?? "—"} / {counts?.all ?? "—"}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
