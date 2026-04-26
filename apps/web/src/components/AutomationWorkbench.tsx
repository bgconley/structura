import {useEffect, useState} from "react";

import {
  acceptFilingSuggestion,
  createContact,
  deferFilingSuggestion,
  dryRunFilingRule,
  listContactMergeSuggestions,
  listContacts,
  listFilingRules,
  listFilingSuggestions,
  listImportStatus,
  listWatchedFolders,
  mergeContact,
  rejectFilingSuggestion,
  saveFilingRule,
  saveWatchedFolder,
} from "../automationApi";
import type {
  Contact,
  ContactMergeSuggestion,
  FilingRule,
  FilingRuleEvaluation,
  FilingRuleWrite,
  FilingSuggestion,
  ImportStatus,
  WatchedFolder,
  WatchedFolderWrite,
} from "../types";
import {AutomationContactsPanel} from "./AutomationContactsPanel";
import {AutomationImportsPanel} from "./AutomationImportsPanel";
import {AutomationRulesPanel} from "./AutomationRulesPanel";
import {AutomationSuggestionsPanel} from "./AutomationSuggestionsPanel";
import {AutomationTabs, type AutomationTab} from "./AutomationTabs";
import {AutomationWatchedPanel} from "./AutomationWatchedPanel";

export function AutomationWorkbench() {
  const [activeTab, setActiveTab] = useState<AutomationTab>("contacts");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [mergeSuggestions, setMergeSuggestions] = useState<ContactMergeSuggestion[]>([]);
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
    const [
      nextContacts,
      nextMergeSuggestions,
      nextRules,
      nextSuggestions,
      nextWatched,
      nextImports,
    ] = await Promise.all([
      listContacts(contactQuery),
      listContactMergeSuggestions(),
      listFilingRules(),
      listFilingSuggestions(),
      listWatchedFolders(),
      listImportStatus(),
    ]);
    setContacts(nextContacts);
    setSelectedContactId((current) => current ?? nextContacts[0]?.id ?? null);
    setMergeSuggestions(nextMergeSuggestions);
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

  async function handleCreateContact(displayName: string) {
    const created = await createContact({
      displayName,
      contactType: "organization",
      aliases: [],
      identifiers: {},
    });
    setContacts((current) => [created, ...current.filter((item) => item.id !== created.id)]);
    setSelectedContactId(created.id);
    setStatus(`Created contact: ${created.displayName}`);
  }

  async function handleMergeContact(suggestion: ContactMergeSuggestion) {
    const merged = await mergeContact(suggestion.sourceContactId, suggestion.targetContactId);
    await refreshAll();
    setSelectedContactId(merged.id);
    setStatus(`Merged contact into ${merged.displayName}`);
  }

  async function handleSaveRule(payload: FilingRuleWrite) {
    const rule = await saveFilingRule(payload);
    setRules((current) => [rule, ...current.filter((item) => item.id !== rule.id)]);
    setStatus(`${rule.enabled ? "Saved" : "Paused"} rule: ${rule.name}`);
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

  async function handleSaveWatchedFolder(payload: WatchedFolderWrite) {
    const watched = await saveWatchedFolder(payload);
    setWatchedFolders((current) => [
      watched,
      ...current.filter((item) => item.id !== watched.id),
    ]);
    setStatus(`${watched.enabled ? "Saved" : "Paused"} watcher: ${watched.path}`);
  }

  return (
    <section className="automation-workbench" aria-label="Automation workbench">
      <header className="automation-hero">
        <p>Transparent Organization Automation</p>
        <h1>Automation Workbench</h1>
        <span>Contacts, filing rules, watched folders, and reviewable suggestions stay auditable.</span>
      </header>
      <AutomationTabs activeTab={activeTab} onChange={setActiveTab} />
      {status ? <p className="automation-status">{status}</p> : null}

      {activeTab === "contacts" ? (
        <AutomationContactsPanel
          contacts={contacts}
          selectedContactId={selectedContactId}
          mergeSuggestions={mergeSuggestions}
          contactQuery={contactQuery}
          onSearch={handleContactSearch}
          onCreate={handleCreateContact}
          onSelect={setSelectedContactId}
          onMerge={handleMergeContact}
        />
      ) : null}

      {activeTab === "rules" ? (
        <AutomationRulesPanel
          rules={rules}
          dryRunResults={dryRunResults}
          status={status}
          onSaveRule={handleSaveRule}
          onDryRun={handleDryRun}
        />
      ) : null}

      {activeTab === "suggestions" ? (
        <AutomationSuggestionsPanel
          suggestions={suggestions}
          onAccept={handleAcceptSuggestion}
          onReject={handleRejectSuggestion}
          onDefer={handleDeferSuggestion}
        />
      ) : null}

      {activeTab === "watched" ? (
        <AutomationWatchedPanel
          watchedFolders={watchedFolders}
          onSave={handleSaveWatchedFolder}
        />
      ) : null}

      {activeTab === "imports" ? <AutomationImportsPanel importStatus={importStatus} /> : null}
    </section>
  );
}
