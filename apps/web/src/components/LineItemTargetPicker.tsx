import {useState} from "react";
import {canReplace, lineLabel} from "../lineItems/decisionIntent";
import type {CanonicalLine, LineCandidate} from "../lineItems/types";
import {RecordedRows} from "./RecordedRows";
import {recordedValue} from "../recordedFactValues";

export function LineItemTargetPicker({candidate, items, onChoose}: {candidate: LineCandidate;
  items: CanonicalLine[]; onChoose: (item: CanonicalLine) => void}) {
  const [query, setQuery] = useState("");
  const allowed = items.filter((item) => canReplace(candidate, item));
  const matching = allowed.filter((item) => [item.description, item.code, item.serviceDate, item.ordinal].join(" ").toLowerCase().includes(query.toLowerCase()));
  return <section className="line-target-picker" aria-label="Choose a recorded line to replace">
    <h3>Choose the recorded line to replace</h3>
    <p>The selected line keeps its position and history. Review the before and after values before saving.</p>
    <label>Find a recorded line<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Description, code, date or line number" /></label>
    {!matching.length ? <p>No matching recorded lines are available for this proposal.</p> : null}
    <RecordedRows items={matching} label="replacement targets" rowKey={(item) => item.id} render={(item) => <article className="line-target-card">
      <h4>{lineLabel(item)}</h4><p>{item.selected ? "Selected" : "Not selected; retained in history"} · {item.serviceDate ?? "No date"} · {item.code ?? "No code"}</p>
      <p>{recordedValue(item.netAmount, "money", item.currency)}</p>
      <button type="button" onClick={() => onChoose(item)}>Review replacement of line {item.ordinal}</button>
    </article>} />
  </section>;
}
