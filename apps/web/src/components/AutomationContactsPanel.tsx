import {FormEvent} from "react";

import type {Contact, ContactMergeSuggestion} from "../types";

export function AutomationContactsPanel({
  contacts,
  selectedContactId,
  mergeSuggestions,
  contactQuery,
  onSearch,
  onCreate,
  onSelect,
  onMerge,
}: {
  contacts: Contact[];
  selectedContactId: string | null;
  mergeSuggestions: ContactMergeSuggestion[];
  contactQuery: string;
  onSearch: (value: string) => Promise<void>;
  onCreate: (displayName: string) => Promise<void>;
  onSelect: (contactId: string) => void;
  onMerge: (suggestion: ContactMergeSuggestion) => Promise<void>;
}) {
  const selectedContact = contacts.find((contact) => contact.id === selectedContactId) ?? contacts[0];
  const contactNames = new Map(contacts.map((contact) => [contact.id, contact.displayName]));

  async function handleCreateContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    if (!name) {
      return;
    }
    await onCreate(name);
    event.currentTarget.reset();
  }

  return (
    <div className="automation-grid">
      <section className="automation-card">
        <h2>Contacts</h2>
        <label>
          Contact search
          <input
            aria-label="Contact search"
            value={contactQuery}
            onChange={(event) => void onSearch(event.target.value)}
            placeholder="Search names, aliases, identifiers"
          />
        </label>
        <form className="inline-form" onSubmit={(event) => void handleCreateContact(event)}>
          <label>
            New contact name
            <input name="name" aria-label="New contact name" placeholder="Delta Dental" />
          </label>
          <button type="submit">Create contact</button>
        </form>
        <div className="automation-list">
          {contacts.map((contact) => (
            <button
              type="button"
              key={contact.id}
              className={contact.id === selectedContact?.id ? "selected" : undefined}
              onClick={() => onSelect(contact.id)}
            >
              <strong>{contact.displayName}</strong>
              <span>{contact.contactType} · {contact.linkedDocumentCount} docs</span>
            </button>
          ))}
        </div>
      </section>
      <section className="automation-card detail-card">
        <h2>{selectedContact?.displayName ?? "No contact selected"}</h2>
        {selectedContact ? (
          <>
            <div className="contact-detail-section">
              <strong>Linked documents</strong>
              <span>{selectedContact.linkedDocumentCount} linked document{selectedContact.linkedDocumentCount === 1 ? "" : "s"}</span>
            </div>
            <p>Aliases: {selectedContact.aliases.join(", ") || "None"}</p>
            <dl>
              {Object.entries(selectedContact.identifiers).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
            </dl>
          </>
        ) : <p>No contacts yet.</p>}
        <section className="automation-mini-panel" aria-label="Duplicate contact suggestions">
          <h3>Duplicate contact suggestions</h3>
          {mergeSuggestions.map((suggestion) => (
            <article key={`${suggestion.sourceContactId}-${suggestion.targetContactId}`} className="merge-row">
              <div>
                <strong>{contactNames.get(suggestion.sourceContactId) ?? "Source contact"}</strong>
                <span>
                  Merge into {contactNames.get(suggestion.targetContactId) ?? "target contact"} · {Math.round(suggestion.confidence * 100)}%
                </span>
              </div>
              <button type="button" onClick={() => void onMerge(suggestion)}>Merge duplicate</button>
            </article>
          ))}
          {!mergeSuggestions.length ? <p>No duplicate contact suggestions.</p> : null}
        </section>
      </section>
    </div>
  );
}
