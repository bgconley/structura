import {useEffect, useRef} from "react";
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
      <label className="command-button">
        {isUploading ? "Uploading..." : "Upload"}
        <input
          type="file"
          disabled={isUploading}
          accept="application/pdf,image/png,image/jpeg,image/tiff,image/webp"
          onChange={(event) => void uploadFile(event.currentTarget.files?.[0])}
        />
      </label>
      <StatusChip tone="green" label="Local-first" />
      <StatusChip tone="green" label="No cloud inference" />
      <StatusChip tone="neutral" label="Search health unreported" />
      <StatusChip tone="neutral" label="Worker status unknown" />
      <SessionMenu session={session} onSignOut={onSignOut} error={sessionError} />
    </header>
  );
}
