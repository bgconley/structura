import {documentSorts, type DocumentSort} from "../documentBrowse";
import type {InboxBrowse} from "../useInboxBrowse";
import {DocumentPagination} from "./DocumentPagination";
import {DocumentTable} from "./DocumentTable";
import "./DocumentBrowse.css";

export function DocumentBrowsePanel({browse, selectedId, uploadFile}: {
  browse: InboxBrowse; selectedId: string | null;
  uploadFile: (file: File | undefined) => Promise<void>;
}) {
  const {list, offset, limit} = browse;
  const beyond = list.total !== null && offset > 0 && offset >= list.total;
  return <section className="document-panel" aria-busy={list.loading}>
    <div className="panel-title"><h2>Documents</h2>
      {list.data ? <p>{list.documents.length} documents displayed</p> : null}</div>
    <div className="document-browse-controls">
      <label>Sort documents <select value={browse.sort} onChange={(event) => browse.setSort(event.target.value as DocumentSort)}>
        {documentSorts.map((sort) => <option key={sort.value} value={sort.value}>{sort.label}</option>)}
      </select></label>
      {browse.hasFilters ? <button type="button" onClick={browse.clearFilters}>Clear Inbox filters</button> : null}
      <button type="button" disabled={list.loading} onClick={() => void list.reload()}>
        {list.loading ? "Refreshing documents…" : "Refresh documents"}
      </button>
    </div>
    <DocumentPagination offset={offset} limit={limit} total={list.total} loading={list.loading}
      onOffset={browse.setOffset} onLimit={browse.setLimit} />
    {list.error ? <div className="empty-state" role="alert">
      <h3>Documents unavailable</h3><p>{list.error.message}</p>
      <button type="button" onClick={() => void list.reload()}>Retry document list</button>
    </div> : !list.data ? <div className="empty-state" role="status">Loading documents…</div>
    : beyond ? <div className="empty-state" role="status">
      <h3>This document page is unavailable</h3>
      <p>The collection may have changed. Your filters and selected document are preserved.</p>
      <div className="document-page-recovery">
        <button type="button" onClick={() => browse.setOffset(0)}>Open first page</button>
        {list.total ? <button type="button" onClick={() => browse.setOffset(Math.floor((list.total! - 1) / limit) * limit)}>Open last page</button> : null}
      </div>
    </div> : list.documents.length === 0 ? <div className="empty-state" role="status">
      <h3>{browse.hasFilters ? "No matching documents" : "No inbox documents yet"}</h3>
      <p>{browse.hasFilters ? "Your Inbox filters are still applied. Change a filter or clear them to browse the collection."
        : "Upload a PDF or supported image to add your first document."}</p>
      {!browse.hasFilters ? <label className="primary-upload">Upload first document
        <input type="file" accept="application/pdf,image/png,image/jpeg,image/tiff,image/webp"
          onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            event.currentTarget.value = "";
            void uploadFile(file);
          }} />
      </label> : null}
    </div> : <DocumentTable documents={list.documents} selectedId={selectedId} setSelectedId={browse.select} />}
    <p className="browse-freshness">New uploads or edits may change which documents appear on each page.</p>
  </section>;
}
