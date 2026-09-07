import {useEffect, useRef} from "react";
import {StatusChip} from "./Status";
import {SessionMenu} from "./SessionMenu";
import {UploadIntake, type UploadIntakeProps} from "./UploadIntake";
import type {SessionInfo} from "../types";

export function TopCommand({
  session,
  onSignOut,
  sessionError,
  query,
  setQuery,
  onSubmitSearch,
  intake,
  uploadsLabel,
  uploadsCount,
  uploadsNeedAttention,
  onOpenUploads,
}: {
  session: SessionInfo;
  onSignOut: () => Promise<void>;
  sessionError: string | null;
  query: string;
  setQuery: (value: string) => void;
  onSubmitSearch: () => void;
  intake: UploadIntakeProps;
  uploadsLabel: string;
  uploadsCount: number;
  uploadsNeedAttention: boolean;
  onOpenUploads: () => void;
}) {
  const searchInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    function focusSearch(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchInput.current?.focus();
        searchInput.current?.select();
      }
    }
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);
  return (
    <header className="top-command">
      <label className="global-search">
        <span aria-hidden="true">S</span>
        <input
          ref={searchInput}
          aria-label="Search documents"
          aria-keyshortcuts="Control+k Meta+k"
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
      <UploadIntake {...intake} />
      <button type="button" className="command-button bulk-import-trigger" onClick={onOpenUploads}>Bulk Import</button>
      <button type="button" className="command-button upload-queue-trigger" aria-label={uploadsLabel} title={uploadsLabel} onClick={onOpenUploads}>Uploads ({uploadsCount})
        {uploadsNeedAttention ? <strong className="upload-attention" aria-hidden="true">!</strong> : null}</button>
      <StatusChip tone="green" label="Local-first" />
      <StatusChip tone="neutral" label="Inference routing unreported" />
      <StatusChip tone="neutral" label="Search health unreported" />
      <StatusChip tone="neutral" label="Worker status unknown" />
      <SessionMenu session={session} onSignOut={onSignOut} error={sessionError} />
    </header>
  );
}
