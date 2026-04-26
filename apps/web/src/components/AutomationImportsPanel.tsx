import type {ImportStatus} from "../types";

export function AutomationImportsPanel({importStatus}: {importStatus: ImportStatus[]}) {
  return (
    <section className="automation-card">
      <h2>Import Status</h2>
      {importStatus.map((item) => (
        <article key={item.watchedFolderId ?? item.path} className="watch-row">
          <div>
            <strong>{item.path ?? "Import source"}</strong>
            <span>{item.enabled === false ? "Paused" : "Enabled"} · last scan {item.lastScanAt ?? "never"}</span>
            <span>{item.acceptedCount} accepted · {item.rejectedCount} rejected · {item.skippedCount} skipped</span>
          </div>
        </article>
      ))}
      {!importStatus.length ? <p>No import activity yet.</p> : null}
    </section>
  );
}
