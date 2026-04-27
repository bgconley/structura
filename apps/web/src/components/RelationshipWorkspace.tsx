import {useEffect, useState} from "react";

import {listDeadlines, listRelationships, listSmartViews, listTimeline} from "../relationshipsApi";
import type {
  DocumentDeadline,
  DocumentRelationship,
  SmartViewSummary,
  TimelineEvent,
} from "../types";
import {formatDate} from "../format";

export function RelationshipWorkspace({
  mode,
  onOpenDocument,
}: {
  mode: "relationships" | "timelines";
  onOpenDocument: (documentId: string) => void;
}) {
  const [relationships, setRelationships] = useState<DocumentRelationship[]>([]);
  const [deadlines, setDeadlines] = useState<DocumentDeadline[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [smartViews, setSmartViews] = useState<SmartViewSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [nextRelationships, nextDeadlines, nextTimeline, nextSmartViews] = await Promise.all([
          listRelationships(),
          listDeadlines(),
          listTimeline(),
          listSmartViews(),
        ]);
        if (!cancelled) {
          setRelationships(nextRelationships);
          setDeadlines(nextDeadlines);
          setTimeline(nextTimeline);
          setSmartViews(nextSmartViews);
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
