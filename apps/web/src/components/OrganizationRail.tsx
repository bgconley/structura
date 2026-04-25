import type {CSSProperties} from "react";

import type {Folder, Tag} from "../types";

export function OrganizationRail({
  folders,
  tags,
  activeFolderId,
  onSelectFolder,
  onCreateFolder,
  onCreateTag,
}: {
  folders: Folder[];
  tags: Tag[];
  activeFolderId: string | null;
  onSelectFolder: (folderId: string | null) => void;
  onCreateFolder: (name: string, folderKind: "manual" | "smart") => Promise<void>;
  onCreateTag: (name: string) => Promise<void>;
}) {
  const manualFolders = folders.filter((folder) => folder.folderKind === "manual");
  const smartFolders = folders.filter((folder) => folder.folderKind === "smart");

  return (
    <section className="organization-rail" aria-label="Folders and tags">
      <div className="org-column">
        <div className="panel-title compact">
          <h2>Folders</h2>
          <button type="button" onClick={() => onSelectFolder(null)}>All documents</button>
        </div>
        <FolderList
          folders={manualFolders}
          activeFolderId={activeFolderId}
          onSelectFolder={onSelectFolder}
          selectable
        />
        <CreateFolderForm onCreateFolder={onCreateFolder} />
      </div>
      <div className="org-column">
        <div className="panel-title compact">
          <h2>Smart Folders</h2>
          <span>{smartFolders.length}</span>
        </div>
        <FolderList
          folders={smartFolders}
          activeFolderId={activeFolderId}
          onSelectFolder={onSelectFolder}
          selectable={false}
        />
      </div>
      <div className="org-column">
        <div className="panel-title compact">
          <h2>Tags</h2>
          <span>{tags.length}</span>
        </div>
        <div className="tag-cloud" aria-label="Available tags">
          {tags.map((tag) => (
            <span key={tag.id} style={{"--tag-color": tag.colorHex ?? "#2563EB"} as CSSProperties}>
              {tag.name}
            </span>
          ))}
        </div>
        <CreateTagForm onCreateTag={onCreateTag} />
      </div>
    </section>
  );
}

function FolderList({
  folders,
  activeFolderId,
  onSelectFolder,
  selectable,
}: {
  folders: Folder[];
  activeFolderId: string | null;
  onSelectFolder: (folderId: string | null) => void;
  selectable: boolean;
}) {
  if (!folders.length) {
    return <p className="empty-copy">No folders yet.</p>;
  }
  return (
    <div className="folder-tree" role="tree">
      {folders.map((folder) => (
        <button
          key={folder.id}
          type="button"
          role="treeitem"
          className={folder.id === activeFolderId ? "selected" : undefined}
          disabled={!selectable}
          onClick={() => onSelectFolder(folder.id)}
        >
          <span aria-hidden="true">{folder.folderKind === "smart" ? "S" : "F"}</span>
          <strong>{folder.name}</strong>
          <small>{folder.path ?? `/${folder.name}`}</small>
          {!selectable ? <em>Dynamic results in Phase 5</em> : null}
        </button>
      ))}
    </div>
  );
}

function CreateFolderForm({
  onCreateFolder,
}: {
  onCreateFolder: (name: string, folderKind: "manual" | "smart") => Promise<void>;
}) {
  return (
    <form
      className="quick-create"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const name = String(form.get("folderName") ?? "");
        const folderKind = String(form.get("folderKind") ?? "manual") as "manual" | "smart";
        void onCreateFolder(name, folderKind).then(() => event.currentTarget.reset());
      }}
    >
      <input name="folderName" placeholder="New folder name" required />
      <select name="folderKind" defaultValue="manual">
        <option value="manual">Manual</option>
        <option value="smart">Smart</option>
      </select>
      <button type="submit">Create</button>
    </form>
  );
}

function CreateTagForm({onCreateTag}: {onCreateTag: (name: string) => Promise<void>}) {
  return (
    <form
      className="quick-create"
      onSubmit={(event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const name = String(form.get("tagName") ?? "");
        void onCreateTag(name).then(() => event.currentTarget.reset());
      }}
    >
      <input name="tagName" placeholder="New tag" required />
      <button type="submit">Create</button>
    </form>
  );
}
