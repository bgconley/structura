export function StatusChip({tone, label}: {tone: "green" | "blue" | "neutral" | "amber"; label: string}) {
  return (
    <span className={`status-chip ${tone}`}>
      <i />
      {label}
    </span>
  );
}

export function ReviewChip({status}: {status: string}) {
  const needsReview = status === "needs_review";
  return (
    <span className={`review-chip ${needsReview ? "amber" : "green"}`}>
      <i />
      {needsReview ? "Needs Review" : status.replace("_", " ")}
    </span>
  );
}

export function TrustLine({ok, label}: {ok: boolean; label: string}) {
  return (
    <div className="trust-line">
      <span className={ok ? "ok" : "warn"} />
      {label}
    </div>
  );
}

export function FactRow({
  label,
  value,
  onJump,
}: {
  label: string;
  value: string;
  onJump?: () => void;
}) {
  return (
    <div className="fact-row">
      <span>{label}</span>
      <strong>{value}</strong>
      {onJump ? <button type="button" onClick={onJump}>go</button> : null}
    </div>
  );
}
