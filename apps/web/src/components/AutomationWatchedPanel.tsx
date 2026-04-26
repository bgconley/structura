import {FormEvent} from "react";

import type {WatchedFolder, WatchedFolderWrite} from "../types";

export function AutomationWatchedPanel({
  watchedFolders,
  onSave,
}: {
  watchedFolders: WatchedFolder[];
  onSave: (payload: WatchedFolderWrite) => Promise<void>;
}) {
  async function handleSaveWatchedFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const path = String(form.get("path") ?? "").trim();
    if (!path) {
      return;
    }
    await onSave({
      path,
      enabled: true,
      policy: {
        allowedExtensions: [".pdf"],
        stabilityDelaySeconds: Number(form.get("stabilityDelaySeconds") ?? 30),
        processedFilePolicy: String(form.get("processedFilePolicy") ?? "leave"),
        recursive: Boolean(form.get("recursive")),
      },
    });
    event.currentTarget.reset();
  }

  return (
    <section className="automation-card">
      <h2>Watched Folders</h2>
      <p className="watch-root">Allowed intake root /srv/structura/imports</p>
      <form className="watch-builder" onSubmit={(event) => void handleSaveWatchedFolder(event)}>
        <label>
          Watch path
          <input name="path" aria-label="Watch path" placeholder="/srv/structura/imports/incoming" />
        </label>
        <label>
          Stability delay
          <input
            name="stabilityDelaySeconds"
            aria-label="Stability delay"
            type="number"
            min="1"
            defaultValue="30"
          />
        </label>
        <label>
          Processed file policy
          <select name="processedFilePolicy" aria-label="Processed file policy" defaultValue="leave">
            <option value="leave">leave</option>
            <option value="move_processed">move_processed</option>
            <option value="move_failed">move_failed</option>
          </select>
        </label>
        <label className="checkbox-label">
          <input name="recursive" aria-label="Recursive import" type="checkbox" />
          Recursive import
        </label>
        <button type="submit">Save watched folder</button>
      </form>
      <div className="automation-list">
        {watchedFolders.map((folder) => (
          <article key={folder.id} className="watch-row">
            <div>
              <strong>{folder.path}</strong>
              <span>{folder.enabled ? "Enabled" : "Paused"} · last scan {folder.lastScanAt ?? "never"}</span>
              <span>{policySummary(folder.policy)}</span>
            </div>
            <button
              type="button"
              onClick={() => void onSave({
                id: folder.id,
                path: folder.path,
                enabled: !folder.enabled,
                policy: folder.policy,
              })}
            >
              {folder.enabled ? "Pause watcher" : "Resume watcher"}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}

function policySummary(policy: Record<string, unknown>): string {
  const stability = Number(policy.stabilityDelaySeconds ?? 30);
  const processed = String(policy.processedFilePolicy ?? "leave");
  const recursive = Boolean(policy.recursive);
  return `${stability}s stability · ${processed} · ${recursive ? "recursive" : "single folder"}`;
}
