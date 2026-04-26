import type {ParseDebugJob, ParseDebugView} from "../types";

export function ParseDebugPanel({
  debug,
  error,
  isLoading,
  onLoad,
}: {
  debug: ParseDebugView | null;
  error: string | null;
  isLoading: boolean;
  onLoad: () => void;
}) {
  const visibleJobs = debug ? debugJobsForDisplay(debug.jobs) : [];

  return (
    <section className="parse-debug-panel">
      <div className="section-title">
        <h3>Parse Debug</h3>
        <button type="button" onClick={onLoad} disabled={isLoading}>
          {isLoading ? "Loading" : "Load"}
        </button>
      </div>
      {error ? <p className="debug-error">{error}</p> : null}
      {debug ? (
        <div className="parse-debug-grid">
          <span>Artifacts <strong>{debug.artifacts.length}</strong></span>
          <span>Pages <strong>{debug.pages.length}</strong></span>
          <span>Chunks <strong>{debug.chunks.length}</strong></span>
          <span>Tables <strong>{debug.tables.length}</strong></span>
          <span>Elements <strong>{debug.elements.length}</strong></span>
          <span>Jobs <strong>{debug.jobs.length}</strong></span>
        </div>
      ) : (
        <p className="debug-copy">Admin-only canonical parse diagnostics load on demand.</p>
      )}
      {debug?.artifacts[0] ? (
        <p className="debug-copy">
          Current artifact: {debug.artifacts[0].assetRole} · {debug.artifacts[0].modelVersion ?? "unknown"}
        </p>
      ) : null}
      {debug?.pages[0]?.textPreview ? (
        <pre>{debug.pages[0].textPreview}</pre>
      ) : null}
      {visibleJobs.length ? (
        <ol className="debug-job-list">
          {visibleJobs.map((job) => (
            <li key={job.jobId}>
              {job.jobType} <strong>{job.status}</strong>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}

function debugJobsForDisplay(jobs: ParseDebugJob[]): ParseDebugJob[] {
  const visible = jobs.slice(0, 6);
  const docling = jobs.find((job) => job.jobType === "docling_convert");
  if (!docling || visible.some((job) => job.jobId === docling.jobId)) {
    return visible;
  }
  return [docling, ...visible.slice(0, 5)];
}
