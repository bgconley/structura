import {useRef, useState} from "react";

type WorkspaceView = "inbox" | "search" | "automation" | "review" | "relationships" | "timelines";
const navItems: {icon: string; label: string; view: WorkspaceView}[] = [
  {icon: "I", label: "Inbox", view: "inbox"},
  {icon: "S", label: "Search", view: "search"},
  {icon: "A", label: "Automation", view: "automation"},
  {icon: "R", label: "Review Queue", view: "review"},
  {icon: "R", label: "Relationships", view: "relationships"},
  {icon: "T", label: "Timelines", view: "timelines"},
];

export function Sidebar({total, active, onNavigate}: {
  total: number | null;
  active: string;
  onNavigate: (view: WorkspaceView) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  return (
    <aside className="sidebar" onKeyDown={(event) => {
      if (event.key === "Escape" && expanded) {
        event.preventDefault(); setExpanded(false); toggle.current?.focus();
      }
    }}>
      <a className="skip-link" href="#route-content" onClick={(event) => {
        event.preventDefault(); document.getElementById("route-content")?.focus();
      }}>Skip to workspace</a>
      <div className="brand-row">
        <span className="logo-mark" aria-hidden="true" />
        <strong>Structura</strong>
        <button ref={toggle} className="navigation-toggle" type="button"
          aria-expanded={expanded} aria-controls="primary-navigation" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Close menu" : "Menu"}
        </button>
      </div>
      <nav id="primary-navigation" aria-label="Primary" className={expanded ? "expanded" : undefined}>
        {navItems.map(({icon, label, view}) => (
          <button key={view} id={`nav-${label.toLowerCase().replaceAll(" ", "-")}`}
            className={active === view ? "active" : undefined} aria-current={active === view ? "page" : undefined}
            type="button" onClick={() => {setExpanded(false); onNavigate(view);}}>
            <span aria-hidden="true">{icon}</span><em>{label}</em>
            {view === "inbox" ? <small title={total === null ? "Document count unavailable" : "Accessible documents"}>{total ?? "—"}</small> : null}
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
