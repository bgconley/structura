import {csrfToken, fetchJson} from "./api";
import type {
  Contact,
  ContactWrite,
  FilingRule,
  FilingRuleEvaluation,
  FilingRuleWrite,
  FilingSuggestion,
  ImportStatus,
  WatchedFolder,
  WatchedFolderWrite,
} from "./types";

type ListResponse<T> = {
  items: T[];
};

export async function listContacts(query = ""): Promise<Contact[]> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  return (await fetchJson<ListResponse<Contact>>(`/api/v1/contacts${params.size ? `?${params}` : ""}`)).items;
}

export async function createContact(payload: ContactWrite): Promise<Contact> {
  return await fetchJson<Contact>("/api/v1/contacts", jsonPost(payload));
}

export async function listFilingRules(): Promise<FilingRule[]> {
  return (await fetchJson<ListResponse<FilingRule>>("/api/v1/filing-rules")).items;
}

export async function saveFilingRule(payload: FilingRuleWrite): Promise<FilingRule> {
  return await fetchJson<FilingRule>("/api/v1/filing-rules", jsonPost(payload));
}

export async function dryRunFilingRule(ruleId: string): Promise<FilingRuleEvaluation[]> {
  return (await fetchJson<ListResponse<FilingRuleEvaluation>>(
    `/api/v1/filing-rules/${ruleId}/dry-run`,
    jsonPost({}),
  )).items;
}

export async function listFilingSuggestions(): Promise<FilingSuggestion[]> {
  return (await fetchJson<ListResponse<FilingSuggestion>>("/api/v1/filing-suggestions")).items;
}

export async function acceptFilingSuggestion(runId: string): Promise<FilingRuleEvaluation> {
  return await fetchJson<FilingRuleEvaluation>(`/api/v1/filing-suggestions/${runId}/accept`, jsonPost({}));
}

export async function rejectFilingSuggestion(runId: string): Promise<{ok: boolean}> {
  return await fetchJson<{ok: boolean}>(`/api/v1/filing-suggestions/${runId}/reject`, jsonPost({}));
}

export async function deferFilingSuggestion(runId: string): Promise<{ok: boolean}> {
  return await fetchJson<{ok: boolean}>(`/api/v1/filing-suggestions/${runId}/defer`, jsonPost({}));
}

export async function listWatchedFolders(): Promise<WatchedFolder[]> {
  return (await fetchJson<ListResponse<WatchedFolder>>("/api/v1/watched-folders")).items;
}

export async function saveWatchedFolder(payload: WatchedFolderWrite): Promise<WatchedFolder> {
  return await fetchJson<WatchedFolder>("/api/v1/watched-folders", jsonPost(payload));
}

export async function listImportStatus(): Promise<ImportStatus[]> {
  return (await fetchJson<ListResponse<ImportStatus>>("/api/v1/import-status")).items;
}

function jsonPost(payload: unknown): RequestInit {
  return {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken(),
    },
    body: JSON.stringify(payload),
  };
}
