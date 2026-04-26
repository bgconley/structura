import {StatusChip} from "./Status";

export function TopCommand({
  query,
  setQuery,
  onSubmitSearch,
  isUploading,
  uploadFile,
}: {
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
      <button className="command-button" type="button">Bulk Import</button>
      <StatusChip tone="green" label="Local-first" />
      <StatusChip tone="green" label="No cloud inference" />
      <StatusChip tone="blue" label="Hybrid search ready" />
      <StatusChip tone="green" label="2 workers active" />
      <span className="avatar">BD</span>
    </header>
  );
}
