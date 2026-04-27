import {FormEvent, useState} from "react";

import {acceptRelationship, createRelationship, rejectRelationship} from "../relationshipsApi";
import type {DocumentDetail, DocumentRelationship, DocumentSummary} from "../types";

const relationshipTypes = [
  "related_to",
  "duplicate_of",
  "invoice_for",
  "receipt_for",
  "eob_for",
  "bill_for",
  "warranty_for",
  "renewal_of",
  "amendment_to",
  "proof_of_payment_for",
  "attachment_to",
];

export function RelationshipPanel({
  document,
  documents,
  onOpenDocument,
  onChanged,
}: {
  document: DocumentDetail | null;
  documents: DocumentSummary[];
  onOpenDocument: (documentId: string) => void;
  onChanged: () => Promise<void>;
}) {
  const [targetDocumentId, setTargetDocumentId] = useState("");
  const [relationshipType, setRelationshipType] = useState("related_to");
  const [comment, setComment] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  if (!document) {
    return (
      <section className="relationship-panel">
        <h3>Related Documents</h3>
        <p>Open a document to manage confirmed and suggested links.</p>
      </section>
    );
  }

  const activeDocument = document;
  const candidates = documents.filter((item) => item.id !== document.id);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!targetDocumentId) {
      setStatus("Choose a related document.");
      return;
    }
    setIsSaving(true);
    setStatus(null);
    try {
      await createRelationship({
        fromDocumentId: activeDocument.id,
        toDocumentId: targetDocumentId,
        relationshipType,
        confidence: 1,
        comment: comment.trim() || undefined,
        evidence: [{
          pageNumber: 1,
          sourceEngine: "human",
          sourceText: comment.trim() || "Manual relationship created in the viewer.",
        }],
      });
      setComment("");
      setTargetDocumentId("");
      setStatus("Relationship saved.");
      await onChanged();
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "Unable to save relationship.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDecision(relationship: DocumentRelationship, action: "accept" | "reject") {
    setIsSaving(true);
    setStatus(null);
    try {
      if (action === "accept") {
        await acceptRelationship(relationship.id, "Accepted from relationship panel.");
        setStatus("Relationship accepted.");
      } else {
        await rejectRelationship(relationship.id, "Rejected from relationship panel.");
        setStatus("Relationship rejected.");
      }
      await onChanged();
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "Unable to update relationship.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="relationship-panel">
      <div className="section-title">
        <h3>Related Documents</h3>
        <span>{document.relationships.length} link{document.relationships.length === 1 ? "" : "s"}</span>
      </div>
      <div className="relationship-list">
        {document.relationships.length ? document.relationships.map((relationship) => (
          <article key={relationship.id} className={`relationship-row ${relationship.status}`}>
            <button type="button" onClick={() => onOpenDocument(relationship.relatedDocumentId)}>
              <strong>{relationship.relatedTitle}</strong>
              <span>{relationship.relationshipType.replaceAll("_", " ")} · {relationship.status}</span>
              {relationship.comment ? <em>{relationship.comment}</em> : null}
            </button>
            {relationship.status === "suggested" ? (
              <div className="relationship-actions">
                <button type="button" disabled={isSaving} onClick={() => void handleDecision(relationship, "accept")}>
                  Accept
                </button>
                <button type="button" disabled={isSaving} onClick={() => void handleDecision(relationship, "reject")}>
                  Reject
                </button>
              </div>
            ) : null}
          </article>
        )) : (
          <p className="pending-copy">No related documents yet. Create a manual link or wait for suggestions.</p>
        )}
      </div>
      <form className="relationship-form" onSubmit={(event) => void handleSubmit(event)}>
        <label>
          Related document
          <select
            aria-label="Related document"
            value={targetDocumentId}
            onChange={(event) => setTargetDocumentId(event.target.value)}
          >
            <option value="">Choose document</option>
            {candidates.map((item) => (
              <option key={item.id} value={item.id}>{item.title}</option>
            ))}
          </select>
        </label>
        <label>
          Relationship type
          <select
            aria-label="Relationship type"
            value={relationshipType}
            onChange={(event) => setRelationshipType(event.target.value)}
          >
            {relationshipTypes.map((item) => (
              <option key={item} value={item}>{item.replaceAll("_", " ")}</option>
            ))}
          </select>
        </label>
        <label>
          Link note
          <input
            aria-label="Relationship note"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            placeholder="Why these documents belong together"
          />
        </label>
        <button type="submit" disabled={isSaving}>Save relationship</button>
      </form>
      {status ? <p className="relationship-status">{status}</p> : null}
    </section>
  );
}
