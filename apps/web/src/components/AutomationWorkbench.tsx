import {FormEvent, useEffect, useState} from "react";

import {
  acceptFilingSuggestion,
  createContact,
  deferFilingSuggestion,
  dryRunFilingRule,
  listContacts,
  listFilingRules,
  listFilingSuggestions,
  listImportStatus,
  listWatchedFolders,
  rejectFilingSuggestion,
  saveFilingRule,
  saveWatchedFolder,
} from "../automationApi";
import type {
  Contact,
  FilingRule,
  FilingRuleEvaluation,
  FilingSuggestion,
  ImportStatus,
  WatchedFolder,
} from "../types";

type AutomationTab = "contacts" | "rules" | "suggestions" | "watched" | "imports";

export function AutomationWorkbench() {
  const [activeTab, setActiveTab] = useState<AutomationTab>("contacts");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [rules, setRules] = useState<FilingRule[]>([]);
  const [suggestions, setSuggestions] = useState<FilingSuggestion[]>([]);
  const [watchedFolders, setWatchedFolders] = useState<WatchedFolder[]>([]);
  const [importStatus, setImportStatus] = useState<ImportStatus[]>([]);
  const [contactQuery, setContactQuery] = useState("");
  const [dryRunResults, setDryRunResults] = useState<FilingRuleEvaluation[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    void refreshAll();
  }, []);

  async function refreshAll() {
    const [nextContacts, nextRules, nextSuggestions, nextWatched, nextImports] = await Promise.all([
      listContacts(contactQuery),
      listFilingRules(),
      listFilingSuggestions(),
      listWatchedFolders(),
      listImportStatus(),
    ]);
    setContacts(nextContacts);
    setSelectedContactId((current) => current ?? nextContacts[0]?.id ?? null);
    setRules(nextRules);
    setSuggestions(nextSuggestions);
    setWatchedFolders(nextWatched);
    setImportStatus(nextImports);
  }

  async function handleContactSearch(value: string) {
    setContactQuery(value);
    const nextContacts = await listContacts(value);
    setContacts(nextContacts);
    setSelectedContactId(nextContacts[0]?.id ?? null);
  }

  async function handleCreateContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    if (!name) {
      return;
    }
    const created = await createContact({
      displayName: name,
      contactType: "organization",
      aliases: [],
      identifiers: {},
    });
    setContacts((current) => [created, ...current.filter((item) => item.id !== created.id)]);
    setSelectedContactId(created.id);
    event.currentTarget.reset();
  }

  async function handleSaveRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("ruleName") ?? "").trim();
    const conditionValue = String(form.get("conditionValue") ?? "").trim();
    const actionTag = String(form.get("actionTag") ?? "").trim();
    if (!name || !conditionValue || !actionTag) {
      return;
    }
    const rule = await saveFilingRule({
      name,
      enabled: true,
      priority: 70,
      reviewRequired: true,
      conditions: [{field: "document_family", op: "eq", value: conditionValue}],
      actions: [{type: "add_tag", tag: actionTag}],
    });
    setRules((current) => [rule, ...current.filter((item) => item.id !== rule.id)]);
    setStatus(`Saved rule: ${rule.name}`);
  }

  async function handleDryRun(rule: FilingRule) {
    const results = await dryRunFilingRule(rule.id);
    setDryRunResults(results);
    const matched = results.filter((result) => result.matched).length;
    setStatus(`Matched ${matched} document${matched === 1 ? "" : "s"}`);
  }

  async function handleAcceptSuggestion(suggestion: FilingSuggestion) {
    await acceptFilingSuggestion(suggestion.runId);
    setStatus("Suggestion accepted");
    await refreshAll();
    setActiveTab("suggestions");
  }

  async function handleRejectSuggestion(suggestion: FilingSuggestion) {
    await rejectFilingSuggestion(suggestion.runId);
    setStatus("Suggestion rejected");
    await refreshAll();
    setActiveTab("suggestions");
  }

  async function handleDeferSuggestion(suggestion: FilingSuggestion) {
    await deferFilingSuggestion(suggestion.runId);
    setStatus("Suggestion deferred");
    await refreshAll();
    setActiveTab("suggestions");
  }

  async function handleSaveWatchedFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const path = String(form.get("path") ?? "").trim();
    if (!path) {
      return;
    }
    const watched = await saveWatchedFolder({
      path,
      enabled: true,
      policy: {
        allowedExtensions: [".pdf"],
        stabilityDelaySeconds: 30,
        processedFilePolicy: "leave",
        recursive: false,
      },
    });
    setWatchedFolders((current) => [
      watched,
      ...current.filter((item) => item.id !== watched.id),
    ]);
    event.currentTarget.reset();
  }

  const selectedContact = contacts.find((contact) => contact.id === selectedContactId) ?? contacts[0];

  return (
    <section className="automation-workbench" aria-label="Automation workbench">
      <header className="automation-hero">
        <p>Transparent Organization Automation</p>
        <h1>Automation Workbench</h1>
        <span>Contacts, filing rules, watched folders, and reviewable suggestions stay auditable.</span>
      </header>
      <div className="automation-tabs" role="tablist" aria-label="Automation sections">
        <TabButton label="Contacts" tab="contacts" activeTab={activeTab} onClick={setActiveTab} />
        <TabButton label="Rules" tab="rules" activeTab={activeTab} onClick={setActiveTab} />
        <TabButton label="Suggestions" tab="suggestions" activeTab={activeTab} onClick={setActiveTab} />
        <TabButton label="Watched Folders" tab="watched" activeTab={activeTab} onClick={setActiveTab} />
        <TabButton label="Import Status" tab="imports" activeTab={activeTab} onClick={setActiveTab} />
      </div>
      {status ? <p className="automation-status">{status}</p> : null}

      {activeTab === "contacts" ? (
        <div className="automation-grid">
          <section className="automation-card">
            <h2>Contacts</h2>
            <label>
              Contact search
              <input
                aria-label="Contact search"
                value={contactQuery}
                onChange={(event) => void handleContactSearch(event.target.value)}
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
                  onClick={() => setSelectedContactId(contact.id)}
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
          </section>
        </div>
      ) : null}

      {activeTab === "rules" ? (
        <section className="automation-card">
          <h2>Rules</h2>
          <form className="rule-builder" onSubmit={(event) => void handleSaveRule(event)}>
            <label>
              Rule name
              <input name="ruleName" aria-label="Rule name" placeholder="Medical EOB filing" />
            </label>
            <label>
              Condition value
              <input name="conditionValue" aria-label="Condition value" placeholder="medical_eob" />
            </label>
            <label>
              Action tag
              <input name="actionTag" aria-label="Action tag" placeholder="insurance" />
            </label>
            <button type="submit">Save rule</button>
          </form>
          <div className="automation-list">
            {rules.map((rule) => (
              <article key={rule.id} className="rule-row">
                <div>
                  <strong>{rule.name}</strong>
                  <span>{rule.enabled ? "Enabled" : "Paused"} · priority {rule.priority ?? 50}</span>
                </div>
                <button type="button" onClick={() => void handleDryRun(rule)}>Dry run</button>
              </article>
            ))}
          </div>
          {dryRunResults.length ? (
            <aside className="dry-run-panel" aria-label="Rule dry-run result">
              <h3>Rule dry-run explanation</h3>
              <p>{status}</p>
              {dryRunResults[0]?.conditions.map((condition, index) => (
                <code key={index}>
                  {String(condition.field)} {String(condition.op)} {String(condition.expected)}
                </code>
              ))}
            </aside>
          ) : null}
        </section>
      ) : null}

      {activeTab === "suggestions" ? (
        <section className="automation-card">
          <h2>Suggested filing</h2>
          {suggestions.map((suggestion) => (
            <article key={suggestion.runId} className="suggestion-row">
              <div>
                <strong>{suggestion.documentTitle}</strong>
                <span>{suggestion.ruleName} · {suggestion.proposedActions.length} proposed actions</span>
              </div>
              <div className="suggestion-actions">
                <button type="button" onClick={() => void handleAcceptSuggestion(suggestion)}>
                  Accept suggestion
                </button>
                <button type="button" onClick={() => void handleRejectSuggestion(suggestion)}>
                  Reject
                </button>
                <button type="button" onClick={() => void handleDeferSuggestion(suggestion)}>
                  Defer
                </button>
              </div>
            </article>
          ))}
          {!suggestions.length ? <p>No pending filing suggestions.</p> : null}
        </section>
      ) : null}

      {activeTab === "watched" ? (
        <section className="automation-card">
          <h2>Watched Folders</h2>
          <form className="inline-form" onSubmit={(event) => void handleSaveWatchedFolder(event)}>
            <label>
              Watch path
              <input name="path" aria-label="Watch path" placeholder="/srv/structura/imports/incoming" />
            </label>
            <button type="submit">Save watched folder</button>
          </form>
          <div className="automation-list">
            {watchedFolders.map((folder) => (
              <article key={folder.id} className="watch-row">
                <strong>{folder.path}</strong>
                <span>{folder.enabled ? "Enabled" : "Paused"} · last scan {folder.lastScanAt ?? "never"}</span>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeTab === "imports" ? (
        <section className="automation-card">
          <h2>Import Status</h2>
          {importStatus.map((item) => (
            <article key={item.watchedFolderId ?? item.path} className="watch-row">
              <strong>{item.path ?? "Import source"}</strong>
              <span>{item.acceptedCount} accepted · {item.rejectedCount} rejected · {item.skippedCount} skipped</span>
            </article>
          ))}
          {!importStatus.length ? <p>No import activity yet.</p> : null}
        </section>
      ) : null}
    </section>
  );
}

function TabButton({
  label,
  tab,
  activeTab,
  onClick,
}: {
  label: string;
  tab: AutomationTab;
  activeTab: AutomationTab;
  onClick: (tab: AutomationTab) => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={activeTab === tab}
      className={activeTab === tab ? "active" : undefined}
      onClick={() => onClick(tab)}
    >
      {label}
    </button>
  );
}
