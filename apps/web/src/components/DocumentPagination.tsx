export function DocumentPagination({offset, limit, total, loading, onOffset, onLimit}: {
  offset: number; limit: number; total: number | null; loading: boolean;
  onOffset: (offset: number) => void; onLimit: (limit: number) => void;
}) {
  const sizes = [25, 50, 100, 200];
  if (!sizes.includes(limit)) sizes.push(limit);
  const beyond = total !== null && total > 0 && offset >= total;
  return <nav className="document-pagination" aria-label="Document pages">
    <p role="status">{total === null ? "Document count unavailable"
      : total === 0 ? "0 matching documents"
      : beyond ? `${total} matching documents; requested page is unavailable`
      : `${offset + 1}–${Math.min(offset + limit, total)} of ${total} documents`}</p>
    <label>Per page <select aria-label="Documents per page" value={limit} onChange={(event) => onLimit(Number(event.target.value))}>
      {sizes.sort((a, b) => a - b).map((size) => <option key={size} value={size}>{size}</option>)}
    </select></label>
    <button id="documents-previous-page" type="button" disabled={loading || total === null || offset === 0}
      onClick={() => onOffset(Math.max(0, offset - limit))}>Previous page</button>
    <button id="documents-next-page" type="button" disabled={loading || total === null || offset + limit >= total}
      onClick={() => onOffset(offset + limit)}>Next page</button>
  </nav>;
}
