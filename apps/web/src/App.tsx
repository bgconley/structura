import { FormEvent, startTransition, useDeferredValue, useEffect, useState } from "react";

const apiBaseUrl = import.meta.env.VITE_STRUCTURA_API_BASE_URL ?? "";

type SessionInfo = {
  displayName?: string;
  email?: string;
  isAuthenticated: boolean;
};

type DocumentSummary = {
  id: string;
  title: string;
  family: string;
  lifecycleState: string;
  reviewStatus: string;
  createdAt: string;
  documentDate?: string;
  amountTotal?: number;
  counterpartyDisplay?: string;
  thumbnailUrl?: string;
  folderPaths?: string[];
};

type DocumentAsset = {
  id: string;
  assetRole: string;
  pageNumber?: number;
  mimeType: string;
  assetUrl: string;
  sha256?: string;
};

type DocumentPage = {
  pageNumber: number;
  width?: number;
  height?: number;
  imageUrl?: string;
};

type DocumentDetail = DocumentSummary & {
  description?: string;
  pages: DocumentPage[];
  assets: DocumentAsset[];
  fields: unknown[];
  lineItems: unknown[];
  extractions: unknown[];
  relationships: unknown[];
  tags: string[];
};

type DocumentListResponse = {
  items: DocumentSummary[];
  total: number;
};

type ViewMode = "inbox" | "viewer";

const navItems = [
  ["I", "Inbox", "18"],
  ["S", "Search", ""],
  ["F", "Folders", ""],
  ["S", "Smart Folders", ""],
  ["R", "Review Queue", "12"],
  ["R", "Relationships", ""],
  ["T", "Timelines", ""],
  ["A", "Analysis", ""],
  ["E", "Exports", ""],
  ["S", "Settings", ""],
];

const filterLabels = [
  "All",
  "Needs Review",
  "Unfiled",
  "Awaiting Classification",
  "Duplicates",
  "Low Confidence",
  "Extracted",
  "Indexed",
];

function csrfToken(): string {
  const cookie = document.cookie
    .split("; ")
    .find((part) => part.startsWith("structura_csrf="));
  return cookie ? decodeURIComponent(cookie.split("=")[1] ?? "") : "";
}

function assetUrl(path?: string): string | undefined {
  if (!path) {
    return undefined;
  }
  return path.startsWith("http") ? path : `${apiBaseUrl}${path}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export default function App() {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("inbox");
  const [activeFilter, setActiveFilter] = useState("All");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [isUploading, setIsUploading] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!session?.isAuthenticated) {
      return;
    }
    void loadDocuments(deferredQuery);
  }, [deferredQuery, session?.isAuthenticated]);

  useEffect(() => {
    if (!selectedId || !session?.isAuthenticated) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedId);
  }, [selectedId, session?.isAuthenticated]);

  async function bootstrap() {
    try {
      const current = await fetchJson<SessionInfo>("/api/v1/auth/session");
      setSession(current);
      await loadDocuments("");
    } catch {
      setSession(null);
    } finally {
      setIsLoading(false);
    }
  }

  async function loadDocuments(search: string) {
    const params = new URLSearchParams();
    if (search.trim()) {
      params.set("q", search.trim());
    }
    const payload = await fetchJson<DocumentListResponse>(
      `/api/v1/documents${params.size ? `?${params}` : ""}`,
    );
    setDocuments(payload.items);
    setTotal(payload.total);
    startTransition(() => {
      setSelectedId((current) => current ?? payload.items[0]?.id ?? null);
    });
  }

  async function loadDetail(documentId: string) {
    try {
      setDetail(await fetchJson<DocumentDetail>(`/api/v1/documents/${documentId}`));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load document detail");
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    try {
      await fetchJson<SessionInfo>("/api/v1/auth/session", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          method: "password",
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      await bootstrap();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Sign-in failed");
    }
  }

  async function uploadFile(file: File | undefined) {
    if (!file) {
      return;
    }
    const body = new FormData();
    body.set("file", file);
    body.set("source", "web_upload");
    body.set("suppliedTitle", file.name.replace(/\.[^.]+$/, ""));
    setIsUploading(true);
    setError(null);
    try {
      await fetchJson("/api/v1/documents", {
        method: "POST",
        headers: {"X-CSRF-Token": csrfToken()},
        body,
      });
      await loadDocuments(deferredQuery);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  const selectedSummary = documents.find((document) => document.id === selectedId) ?? documents[0];
  const selected = detail ?? selectedSummary ?? null;

  if (isLoading) {
    return <div className="boot-screen">Loading Structura...</div>;
  }

  if (!session?.isAuthenticated) {
    return <LoginScreen error={error} onSubmit={handleLogin} />;
  }

  return (
    <div className="app-shell">
      <Sidebar total={total} />
      <main className="app-main">
        <TopCommand
          query={query}
          setQuery={setQuery}
          isUploading={isUploading}
          uploadFile={uploadFile}
        />
        {viewMode === "viewer" && selected ? (
          <Viewer
            document={detail}
            summary={selectedSummary}
            onBack={() => setViewMode("inbox")}
          />
        ) : (
          <Inbox
            documents={documents}
            total={total}
            selectedId={selectedId}
            selected={selected}
            detail={detail}
            error={error}
            activeFilter={activeFilter}
            setActiveFilter={setActiveFilter}
            setSelectedId={setSelectedId}
            openViewer={() => setViewMode("viewer")}
            uploadFile={uploadFile}
          />
        )}
      </main>
    </div>
  );
}

function LoginScreen({
  error,
  onSubmit,
}: {
  error: string | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <main className="login-screen">
      <section className="login-card">
        <span className="logo-mark" />
        <h1>Structura</h1>
        <p>Sign in to open the local-first evidence workbench.</p>
        <form onSubmit={onSubmit}>
          <label>
            Email
            <input name="email" type="email" required autoComplete="email" />
          </label>
          <label>
            Password
            <input name="password" type="password" required minLength={8} autoComplete="current-password" />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button type="submit">Sign in</button>
        </form>
      </section>
    </main>
  );
}

function Sidebar({total}: {total: number}) {
  return (
    <aside className="sidebar">
      <div className="brand-row">
        <span className="logo-mark" />
        <strong>Structura</strong>
      </div>
      <nav aria-label="Primary">
        {navItems.map(([icon, label, badge]) => (
          <a key={label} className={label === "Inbox" ? "active" : undefined} href="#">
            <span>{icon}</span>
            <em>{label}</em>
            {label === "Inbox" ? <small>{total || badge}</small> : null}
            {label === "Review Queue" ? <b>12</b> : null}
          </a>
        ))}
      </nav>
      <section className="machine-health" aria-label="Machine health">
        <h2>Machine Health</h2>
        <HealthLine title="Backup healthy" detail="Last backup: 2h ago" />
        <HealthLine title="Storage healthy" detail="68% used" />
        <HealthLine title="Workers active" detail="2 of 2 online" />
      </section>
    </aside>
  );
}

function HealthLine({title, detail}: {title: string; detail: string}) {
  return (
    <div className="health-line">
      <span />
      <p>{title}</p>
      <small>{detail}</small>
    </div>
  );
}

function TopCommand({
  query,
  setQuery,
  isUploading,
  uploadFile,
}: {
  query: string;
  setQuery: (value: string) => void;
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

function Inbox({
  documents,
  total,
  selectedId,
  selected,
  detail,
  error,
  activeFilter,
  setActiveFilter,
  setSelectedId,
  openViewer,
  uploadFile,
}: {
  documents: DocumentSummary[];
  total: number;
  selectedId: string | null;
  selected: DocumentSummary | DocumentDetail | null;
  detail: DocumentDetail | null;
  error: string | null;
  activeFilter: string;
  setActiveFilter: (filter: string) => void;
  setSelectedId: (id: string) => void;
  openViewer: () => void;
  uploadFile: (file: File | undefined) => Promise<void>;
}) {
  const needsReview = documents.filter((document) => document.reviewStatus === "needs_review").length;
  const unfiled = documents.filter((document) => !(document.folderPaths?.length)).length;

  return (
    <section className="home-grid">
      <div className="workspace">
        <div className="page-heading">
          <div>
            <h1>Document Operations</h1>
            <p>Overview of document review, filing, and trust state.</p>
          </div>
          <button type="button" onClick={openViewer} disabled={!selected}>
            Open Viewer
          </button>
        </div>
        <div className="metrics-row">
          <Metric label="Needs Review" value={needsReview} detail="Review required" tone="amber" />
          <Metric label="Unfiled Documents" value={unfiled} detail="Awaiting filing" tone="blue" />
          <Metric label="Awaiting Classification" value={total} detail="Phase 3 ready" tone="blue" />
          <Metric label="Missing Required Fields" value={0} detail="Needs attention" tone="amber" />
          <Metric label="Duplicate Suspects" value={0} detail="Exact hash flagged" tone="amber" />
          <Metric label="Recent Uploads" value={total} detail="Visible in inbox" tone="blue" />
        </div>
        <div className="filter-row" aria-label="Document filters">
          {filterLabels.map((filter) => (
            <button
              key={filter}
              className={filter === activeFilter ? "selected" : undefined}
              type="button"
              onClick={() => setActiveFilter(filter)}
            >
              <span />
              {filter}
            </button>
          ))}
        </div>
        {error ? <div className="inline-error">{error}</div> : null}
        <DocumentTable
          documents={documents}
          selectedId={selectedId}
          setSelectedId={setSelectedId}
          uploadFile={uploadFile}
        />
        <PipelineSummary total={total} previewed={documents.filter((document) => document.thumbnailUrl).length} />
      </div>
      <Inspector selected={selected} detail={detail} openViewer={openViewer} />
    </section>
  );
}

function Metric({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  tone: "blue" | "amber";
}) {
  return (
    <article className="metric-card">
      <p>{label}</p>
      <strong className={tone}>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function DocumentTable({
  documents,
  selectedId,
  setSelectedId,
  uploadFile,
}: {
  documents: DocumentSummary[];
  selectedId: string | null;
  setSelectedId: (id: string) => void;
  uploadFile: (file: File | undefined) => Promise<void>;
}) {
  return (
    <section className="document-panel">
      <div className="panel-title">
        <h2>Priority Document Activity</h2>
        <p>1-{Math.min(documents.length, 7)} of {documents.length} documents</p>
      </div>
      {documents.length === 0 ? (
        <div className="empty-state">
          <h3>No inbox documents yet</h3>
          <p>Upload a PDF or image to create the first document row and protected original asset.</p>
          <label className="primary-upload">
            Upload first document
            <input
              type="file"
              accept="application/pdf,image/png,image/jpeg,image/tiff,image/webp"
              onChange={(event) => void uploadFile(event.currentTarget.files?.[0])}
            />
          </label>
        </div>
      ) : (
        <table>
          <thead>
            <tr>
              <th aria-label="select" />
              <th>Document</th>
              <th>Family</th>
              <th>Counterparty</th>
              <th>Date</th>
              <th>Key Amount</th>
              <th>Folder</th>
              <th>Review Status</th>
              <th>Pipeline</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr
                key={document.id}
                className={document.id === selectedId ? "selected" : undefined}
                onClick={() => setSelectedId(document.id)}
              >
                <td><span className="row-check" /></td>
                <td>
                  <div className="doc-cell">
                    {document.thumbnailUrl ? (
                      <img src={assetUrl(document.thumbnailUrl)} alt="" />
                    ) : (
                      <span className="thumb-skeleton" />
                    )}
                    <div>
                      <strong>{document.title}</strong>
                      <small>#{document.id.slice(0, 13).toUpperCase()}</small>
                    </div>
                  </div>
                </td>
                <td>{familyLabel(document.family)}</td>
                <td>{document.counterpartyDisplay ?? "Pending"}</td>
                <td>{formatDate(document.documentDate)}</td>
                <td>{formatAmount(document.amountTotal)}</td>
                <td>{document.folderPaths?.[0]?.replace("/", "") || "Unfiled"}</td>
                <td><ReviewChip status={document.reviewStatus} /></td>
                <td><span className="pipeline-state">Ingested</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Inspector({
  selected,
  detail,
  openViewer,
}: {
  selected: DocumentSummary | DocumentDetail | null;
  detail: DocumentDetail | null;
  openViewer: () => void;
}) {
  if (!selected) {
    return (
      <aside className="inspector">
        <h2>No document selected</h2>
        <p>Upload or select a row to inspect evidence and document state.</p>
      </aside>
    );
  }
  const original = detail?.assets.find((asset) => asset.assetRole === "original");
  const sha = original?.sha256 ? `${original.sha256.slice(0, 12)}...` : "Stored after upload";

  return (
    <aside className="inspector">
      <h2>{selected.title}</h2>
      <p>{familyLabel(selected.family)}</p>
      <div className="inspector-chips">
        <ReviewChip status={selected.reviewStatus} />
        <StatusChip tone="blue" label="86% confidence" />
      </div>
      <p className="fingerprint">Immutable original · SHA-256 {sha}</p>
      <div className="evidence-preview">
        {selected.thumbnailUrl ? <img src={assetUrl(selected.thumbnailUrl)} alt="" /> : <span className="thumb-skeleton large" />}
        <small>Evidence cue anchors the selected field</small>
      </div>
      <section className="fields-block">
        <div className="section-title">
          <h3>Extracted Fields</h3>
          <button type="button">Jump to evidence</button>
        </div>
        {detail?.fields.length ? (
          <p>Fields loaded.</p>
        ) : (
          <p className="pending-copy">Extraction fields are pending Phase 3. The original and preview are already protected.</p>
        )}
      </section>
      <section className="actions-block">
        <h3>Document actions</h3>
        <button type="button" className="primary" onClick={openViewer}>Open viewer</button>
        {original ? (
          <a href={assetUrl(original.assetUrl)} download>
            Download original
          </a>
        ) : null}
        <button type="button">File document</button>
      </section>
      <section className="related-block">
        <h3>Related Documents</h3>
        <p>Relationship suggestions are prepared for Phase 7.</p>
      </section>
    </aside>
  );
}

function PipelineSummary({total, previewed}: {total: number; previewed: number}) {
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

function Viewer({
  document,
  summary,
  onBack,
}: {
  document: DocumentDetail | null;
  summary?: DocumentSummary;
  onBack: () => void;
}) {
  const active = document ?? summary;
  const original = document?.assets.find((asset) => asset.assetRole === "original");
  const preview = document?.pages[0]?.imageUrl;

  if (!active) {
    return null;
  }

  return (
    <section className="viewer-grid">
      <div className="viewer-heading">
        <div>
          <h1>Document Viewer</h1>
          <p>Read the original document in-app while preserving trust and provenance context.</p>
        </div>
        <button type="button" onClick={onBack}>Back to Inbox</button>
      </div>
      <aside className="page-rail">
        {[1, 2, 3, 4, 5].map((page) => (
          <button className={page === 1 ? "selected" : undefined} type="button" key={page}>
            <span className="rail-thumb" />
            <small>{page}</small>
          </button>
        ))}
      </aside>
      <section className="viewer-card">
        <div className="viewer-card-title">
          <h2>{active.title}</h2>
          <StatusChip tone="green" label="Immutable original" />
          <StatusChip tone="neutral" label="Extraction pending" />
        </div>
        <div className="rendered-page">
          {preview ? (
            <img src={assetUrl(preview)} alt={`Preview of ${active.title}`} />
          ) : original?.mimeType === "application/pdf" ? (
            <iframe src={assetUrl(original.assetUrl)} title={active.title} />
          ) : (
            <div className="preview-fallback">
              <span className="thumb-skeleton large" />
              <p>Preview generation is pending. The protected original is available.</p>
            </div>
          )}
        </div>
        <div className="viewer-actions">
          <button type="button" className="primary">Open review</button>
          {original ? <a href={assetUrl(original.assetUrl)} download>Download original</a> : null}
        </div>
      </section>
      <aside className="facts-panel">
        <h2>Document Facts</h2>
        <ReviewChip status={active.reviewStatus} />
        <p>
          {document?.description
            ?? `${familyLabel(active.family)} document preserved as an immutable original.`}
        </p>
        <h3>Trust state</h3>
        <TrustLine ok label="Original stored immutably" />
        <TrustLine ok label="SHA-256 fingerprint stored" />
        <TrustLine ok={Boolean(preview)} label={preview ? "Preview asset available" : "Preview pending"} />
        <TrustLine ok={active.reviewStatus !== "needs_review"} label="Fields pending review" />
        <h3>Key fields</h3>
        <FactRow label="Family" value={familyLabel(active.family)} />
        <FactRow label="Counterparty" value={active.counterpartyDisplay ?? "Pending extraction"} />
        <FactRow label="Date" value={formatDate(active.documentDate)} />
        <FactRow label="Folder" value={active.folderPaths?.[0] ?? "Unfiled"} />
        <button type="button" className="primary">Review extracted fields</button>
        <div className="two-actions">
          <button type="button">File document</button>
          <button type="button">Link document</button>
        </div>
      </aside>
    </section>
  );
}

function StatusChip({tone, label}: {tone: "green" | "blue" | "neutral"; label: string}) {
  return (
    <span className={`status-chip ${tone}`}>
      <i />
      {label}
    </span>
  );
}

function ReviewChip({status}: {status: string}) {
  const needsReview = status === "needs_review";
  return (
    <span className={`review-chip ${needsReview ? "amber" : "green"}`}>
      <i />
      {needsReview ? "Needs Review" : status.replace("_", " ")}
    </span>
  );
}

function TrustLine({ok, label}: {ok: boolean; label: string}) {
  return (
    <div className="trust-line">
      <span className={ok ? "ok" : "warn"} />
      {label}
    </div>
  );
}

function FactRow({label, value}: {label: string; value: string}) {
  return (
    <div className="fact-row">
      <span>{label}</span>
      <strong>{value}</strong>
      <button type="button">go</button>
    </div>
  );
}

function familyLabel(family: string): string {
  return family.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value?: string): string {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat(undefined, {month: "short", day: "numeric", year: "numeric"}).format(
    new Date(value),
  );
}

function formatAmount(value?: number): string {
  if (typeof value !== "number") {
    return "-";
  }
  return new Intl.NumberFormat(undefined, {style: "currency", currency: "USD"}).format(value);
}
