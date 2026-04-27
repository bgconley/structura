import {useEffect, useState} from "react";

import {listContacts} from "../automationApi";
import {listDeadlines, listRelationships, listSmartViews, listTimeline} from "../relationshipsApi";
import type {
  Contact,
  DocumentDeadline,
  DocumentRelationship,
  DocumentSummary,
  SmartViewSummary,
  TimelineEvent,
} from "../types";
import {formatDate} from "../format";

export function RelationshipWorkspace({
  mode,
  documents,
  onOpenDocument,
}: {
  mode: "relationships" | "timelines";
  documents: DocumentSummary[];
  onOpenDocument: (documentId: string) => void;
}) {
  const [relationships, setRelationships] = useState<DocumentRelationship[]>([]);
  const [deadlines, setDeadlines] = useState<DocumentDeadline[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [smartViews, setSmartViews] = useState<SmartViewSummary[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [timelineScope, setTimelineScope] = useState<"all" | "document" | "contact">("all");
  const [timelineDocumentId, setTimelineDocumentId] = useState("");
  const [timelineContactId, setTimelineContactId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [nextRelationships, nextDeadlines, nextSmartViews, nextContacts] = await Promise.all([
          listRelationships(),
          listDeadlines(),
          listSmartViews(),
          listContacts(),
        ]);
        if (!cancelled) {
          setRelationships(nextRelationships);
          setDeadlines(nextDeadlines);
          setSmartViews(nextSmartViews);
          setContacts(nextContacts);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Unable to load relationships.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const params =
          timelineScope === "document" && timelineDocumentId
            ? {documentId: timelineDocumentId}
            : timelineScope === "contact" && timelineContactId
              ? {contactId: timelineContactId}
              : {};
        const nextTimeline = await listTimeline(params);
        if (!cancelled) {
          setTimeline(nextTimeline);
          setError(null);
        }
      } catch (exc) {
        if (!cancelled) {
          setError(exc instanceof Error ? exc.message : "Unable to load timeline.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [timelineScope, timelineDocumentId, timelineContactId]);

  const heading = mode === "timelines" ? "Document Timelines" : "Relationship Workbench";

  return (
    <section className="relationship-workbench">
      <div className="relationship-heading">
        <div>
          <h1>{heading}</h1>
          <p>Navigate document links, deadlines, and entity timelines without exposing hidden documents.</p>
        </div>
      </div>
      {error ? <div className="inline-error">{error}</div> : null}
      <div className="relationship-workbench-grid">
        <section className="relationship-card">
          <h2>Suggested and confirmed links</h2>
          <div className="relationship-list wide">
            {relationships.slice(0, 12).map((item) => (
              <button key={item.id} type="button" onClick={() => onOpenDocument(item.documentId)}>
                <strong>{item.relatedTitle}</strong>
                <span>{item.relationshipType.replaceAll("_", " ")} · {item.status}</span>
                {item.comment ? <em>{item.comment}</em> : null}
              </button>
            ))}
            {!relationships.length ? <p>No relationships yet.</p> : null}
          </div>
        </section>
        <section className="relationship-card">
          <h2>Open deadlines</h2>
          <div className="deadline-list">
            {deadlines.slice(0, 10).map((item) => (
              <button key={item.id} type="button" onClick={() => onOpenDocument(item.documentId)}>
                <strong>{item.deadlineType.replaceAll("_", " ")}</strong>
                <span>{item.documentTitle}</span>
                <em>{formatDate(item.dueOn)} · {item.status}</em>
              </button>
            ))}
            {!deadlines.length ? <p>No open deadlines detected.</p> : null}
          </div>
        </section>
        <section className="relationship-card">
          <h2>Smart views</h2>
          <div className="smart-view-list">
            {smartViews.map((item) => (
              <article key={item.key}>
                <strong>{item.title}</strong>
                <span>{item.description}</span>
                <b>{item.count}</b>
              </article>
            ))}
          </div>
        </section>
        <section className="relationship-card timeline-card">
          <h2>Timeline</h2>
          <div className="timeline-controls">
            <label>
              Timeline scope
              <select
                aria-label="Timeline scope"
                value={timelineScope}
                onChange={(event) => {
                  setTimelineScope(event.target.value as "all" | "document" | "contact");
                  setTimelineDocumentId("");
                  setTimelineContactId("");
                }}
              >
                <option value="all">All readable documents</option>
                <option value="document">Document</option>
                <option value="contact">Contact</option>
              </select>
            </label>
            {timelineScope === "document" ? (
              <label>
                Timeline document
                <select
                  aria-label="Timeline document"
                  value={timelineDocumentId}
                  onChange={(event) => setTimelineDocumentId(event.target.value)}
                >
                  <option value="">Choose document</option>
                  {documents.map((item) => (
                    <option key={item.id} value={item.id}>{item.title}</option>
                  ))}
                </select>
              </label>
            ) : null}
            {timelineScope === "contact" ? (
              <label>
                Timeline contact
                <select
                  aria-label="Timeline contact"
                  value={timelineContactId}
                  onChange={(event) => setTimelineContactId(event.target.value)}
                >
                  <option value="">Choose contact</option>
                  {contacts.map((item) => (
                    <option key={item.id} value={item.id}>{item.displayName}</option>
                  ))}
                </select>
              </label>
            ) : null}
          </div>
          <div className="timeline-list">
            {timeline.slice(0, 16).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => item.documentId ? onOpenDocument(item.documentId) : undefined}
              >
                <time>{formatDate(item.occurredOn)}</time>
                <strong>{item.title}</strong>
                <span>{item.eventType}{item.status ? ` · ${item.status}` : ""}</span>
              </button>
            ))}
            {!timeline.length ? <p>No timeline events yet.</p> : null}
          </div>
        </section>
      </div>
    </section>
  );
}
