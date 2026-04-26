export function formatCondition(condition: Record<string, unknown>): string {
  return [
    String(condition.field ?? "field"),
    String(condition.op ?? "op"),
    String(condition.expected ?? condition.value ?? ""),
  ].filter(Boolean).join(" ");
}

export function formatAction(action: Record<string, unknown>): string {
  const type = String(action.type ?? "action");
  if (type === "add_tag") {
    return `add tag ${String(action.tag ?? "")}`;
  }
  if (type === "set_sensitivity") {
    return `set sensitivity ${String(action.value ?? "")}`;
  }
  if (type === "set_document_type") {
    return `set document type ${String(action.value ?? "")}`;
  }
  if (type === "create_review_task") {
    return `create review task ${String(action.value ?? "")}`;
  }
  if (type === "add_folder" || type === "set_primary_folder") {
    return `${type.replaceAll("_", " ")} ${String(action.folder_path ?? action.folderId ?? action.folder_id ?? "")}`;
  }
  return type.replaceAll("_", " ");
}
