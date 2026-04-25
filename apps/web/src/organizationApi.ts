import {csrfToken, fetchJson} from "./api";
import type {
  DocumentDetail,
  DocumentOrganizationWrite,
  Folder,
  FolderWrite,
  Tag,
  TagWrite,
} from "./types";

type ListResponse<T> = {
  items: T[];
};

export async function listFolders(): Promise<Folder[]> {
  return (await fetchJson<ListResponse<Folder>>("/api/v1/folders")).items;
}

export async function createFolder(payload: FolderWrite): Promise<Folder> {
  return await fetchJson<Folder>("/api/v1/folders", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken(),
    },
    body: JSON.stringify(payload),
  });
}

export async function listTags(): Promise<Tag[]> {
  return (await fetchJson<ListResponse<Tag>>("/api/v1/tags")).items;
}

export async function createTag(payload: TagWrite): Promise<Tag> {
  return await fetchJson<Tag>("/api/v1/tags", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken(),
    },
    body: JSON.stringify(payload),
  });
}

export async function updateDocumentOrganization(
  documentId: string,
  payload: DocumentOrganizationWrite,
): Promise<DocumentDetail> {
  return await fetchJson<DocumentDetail>(`/api/v1/documents/${documentId}/organization`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken(),
    },
    body: JSON.stringify(payload),
  });
}
