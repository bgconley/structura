import "./Status.css";

type ReviewPresentation = {tone: "neutral" | "amber" | "rejected" | "green"; label: string};
const reviewStates = new Map<string, ReviewPresentation>([
  ["unreviewed", {tone: "neutral", label: "Unreviewed"}],
  ["needs_review", {tone: "amber", label: "Needs Review"}],
  ["rejected", {tone: "rejected", label: "Rejected"}],
  ["auto_accepted", {tone: "green", label: "Auto accepted"}],
  ["user_confirmed", {tone: "green", label: "User confirmed"}],
  ["user_corrected", {tone: "green", label: "User corrected"}],
]);

export function reviewPresentation(status: string | null | undefined): ReviewPresentation {
  return reviewStates.get(status ?? "") ?? {tone: "neutral", label: "Review status unknown"};
}

export function StatusChip({tone, label}: {tone: "green" | "blue" | "neutral" | "amber"; label: string}) {
  return (
    <span className={`status-chip ${tone}`}>
      <i aria-hidden="true" />
      {label}
    </span>
  );
}

export function ReviewChip({status}: {status: string | null | undefined}) {
  const {tone, label} = reviewPresentation(status);
  return (
    <span className={`review-chip ${tone}`}>
      <i aria-hidden="true" />
      {label}
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
