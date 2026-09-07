import {useEffect, useId, useRef, useState, type ReactNode} from "react";

export function RecordedRows<T>({items, label, focusIndex = -1, render, rowKey}: {
  items: T[]; label: string; focusIndex?: number; render: (item: T) => ReactNode; rowKey: (item: T) => string;
}) {
  const pageSize = 10;
  const [requestedPage, setPage] = useState(Math.max(0, Math.floor(focusIndex / pageSize)));
  const list = useRef<HTMLOListElement>(null);
  const id = useId();
  const lastPage = Math.max(0, Math.ceil(items.length / pageSize) - 1);
  const page = Math.min(requestedPage, lastPage);
  useEffect(() => { if (focusIndex >= 0) setPage(Math.floor(focusIndex / pageSize)); }, [focusIndex]);
  function changePage(next: number) {
    setPage(next);
    list.current?.focus();
  }
  return <>
    <p role="status" className="recorded-count">{items.length ? `${page * pageSize + 1}–${Math.min((page + 1) * pageSize, items.length)} of ${items.length}` : "0"} {label}</p>
    <ol id={id} className="recorded-rows" ref={list} tabIndex={-1} aria-label={label} start={page * pageSize + 1}>
      {items.slice(page * pageSize, (page + 1) * pageSize).map((item) => <li key={rowKey(item)}>{render(item)}</li>)}
    </ol>
    {items.length > pageSize ? <nav className="recorded-paging" aria-label={`${label} pages`}>
      <button type="button" aria-controls={id} disabled={page === 0} onClick={() => changePage(page - 1)}>Previous</button>
      <label>Page<select value={page + 1} onChange={(event) => changePage(Number(event.target.value) - 1)}>
        {Array.from({length: lastPage + 1}, (_, index) => <option key={index} value={index + 1}>{index + 1}</option>)}
      </select></label>
      <span>of {lastPage + 1}</span>
      <button type="button" aria-controls={id} disabled={page === lastPage} onClick={() => changePage(page + 1)}>Next</button>
    </nav> : null}
  </>;
}
