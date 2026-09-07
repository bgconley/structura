import {StatusChip} from "./Status";
import {SessionMenu} from "./SessionMenu";
import type {SessionInfo} from "../types";

export function TopCommand({
  session,
  onSignOut,
  sessionError,
  query,
  setQuery,
  onSubmitSearch,
  isUploading,
  uploadFile,
}: {
  session: SessionInfo;
  onSignOut: () => Promise<void>;
  sessionError: string | null;
  query: string;
  setQuery: (value: string) => void;
  onSubmitSearch: () => void;
  isUploading: boolean;
  uploadFile: (file: File | undefined) => Promise<void>;
}) {
  return (
    <header className="top-command">
      <label className="global-search">
        <span>S</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              onSubmitSearch();
            }
          }}
          placeholder="Search receipts, EOBs, warranties, claims, taxes..."
        />
        <kbd>Ctrl / ⌘ K</kbd>
      </label>
      <label className="command-button">
        {isUploading ? "Uploading..." : "Upload"}
        <input
          type="file"
          accept="application/pdf,image/png,image/jpeg,image/tiff,image/webp"
          onChange={(event) => void uploadFile(event.currentTarget.files?.[0])}
        />
      </label>
      <button className="command-button" type="button" disabled title="Bulk import is not available yet">Bulk Import</button>
      <StatusChip tone="green" label="Local-first" />
      <StatusChip tone="green" label="No cloud inference" />
      <StatusChip tone="neutral" label="Search health unreported" />
      <StatusChip tone="neutral" label="Worker status unknown" />
      <SessionMenu session={session} onSignOut={onSignOut} error={sessionError} />
    </header>
  );
}
