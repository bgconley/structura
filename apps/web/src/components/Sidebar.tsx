const navItems = [
  ["I", "Inbox"],
  ["S", "Search"],
  ["A", "Automation"],
  ["F", "Folders"],
  ["S", "Smart Folders"],
  ["R", "Review Queue"],
  ["R", "Relationships"],
  ["T", "Timelines"],
  ["A", "Analysis"],
  ["E", "Exports"],
  ["S", "Settings"],
];

export function Sidebar({
  total,
  active,
  onNavigate,
}: {
  total: number;
  active: string;
  onNavigate: (view: "inbox" | "review" | "search" | "automation" | "relationships" | "timelines") => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand-row">
        <span className="logo-mark" />
        <strong>Structura</strong>
      </div>
      <nav aria-label="Primary">
        {navItems.map(([icon, label]) => (
          <button
            key={label}
            id={`nav-${label.toLowerCase().replaceAll(" ", "-")}`}
            className={
              (label === "Inbox" && active === "inbox")
              || (label === "Search" && active === "search")
              || (label === "Automation" && active === "automation")
              || (label === "Review Queue" && active === "review")
              || (label === "Relationships" && active === "relationships")
              || (label === "Timelines" && active === "timelines")
                ? "active"
                : undefined
            }
            type="button"
            disabled={!["Inbox", "Search", "Automation", "Review Queue", "Relationships", "Timelines"].includes(label)}
            onClick={() => {
              if (label === "Review Queue") {
                onNavigate("review");
              } else if (label === "Automation") {
                onNavigate("automation");
              } else if (label === "Relationships") {
                onNavigate("relationships");
              } else if (label === "Timelines") {
                onNavigate("timelines");
              } else if (label === "Search") {
                onNavigate("search");
              } else {
                onNavigate("inbox");
              }
            }}
          >
            <span>{icon}</span>
            <em>{label}</em>
            {label === "Inbox" ? <small>{total}</small> : null}
          </button>
        ))}
      </nav>
      <section className="machine-health" aria-label="Machine health">
        <h2>Machine Health</h2>
        <HealthLine title="Backup status unknown" detail="No backup observation available" />
        <HealthLine title="Storage status unknown" detail="Usage has not been reported" />
        <HealthLine title="Worker status unknown" detail="No worker observation available" />
      </section>
    </aside>
  );
}

function HealthLine({title, detail}: {title: string; detail: string}) {
  return (
    <div className="health-line">
      <span style={{background: "var(--muted)"}} />
      <p>{title}</p>
      <small>{detail}</small>
    </div>
  );
}
