export function PipelineSummary({total, previewed}: {total: number; previewed: number}) {
  const stages = [
    ["Ingest", total, total, "green"],
    ["Preview", previewed, total, previewed === total ? "green" : "amber"],
    ["Docling parse", 0, total, "neutral"],
    ["Classification", 0, total, "neutral"],
    ["Extraction", 0, total, "neutral"],
    ["Indexing", 0, total, "neutral"],
  ];
  return (
    <section className="pipeline-panel">
      <div className="panel-title">
        <h2>Pipeline & Indexing Summary</h2>
        <button type="button">Pipeline details</button>
      </div>
      <div className="stage-row">
        {stages.map(([label, done, count, tone]) => (
          <article className={`stage-card ${tone}`} key={label}>
            <span />
            <strong>{label}</strong>
            <small>{done} / {count}</small>
          </article>
        ))}
      </div>
    </section>
  );
}
