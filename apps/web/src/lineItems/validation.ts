// Fail-closed read primitives preserve exact decimal and revision strings.
export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
export const uuid = (v: unknown): v is string => typeof v === "string" && /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i.test(v);
export const nullableUuid = (v: unknown) => v === null || uuid(v);
export const text = (v: unknown): v is string => typeof v === "string";
export const nullableText = (v: unknown) => v === null || text(v);
export const digest = (v: unknown) => text(v) && /^[a-f\d]{64}$/.test(v);
export const timestamp = (v: unknown) => text(v) && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
export const natural = (v: unknown): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
export const slot = (v: Record<string, unknown>) => ["generic", "receipt_item", "invoice_item", "service_line", "payment", "tax", "adjustment", "fee"].includes(String(v.lineItemType))
  && natural(v.ordinal) && v.ordinal > 0 && v.ordinal <= 2147483647;
export const sameSlot = (a: {lineItemType: unknown; ordinal: unknown}, b: {lineItemType: unknown; ordinal: unknown}) => a.lineItemType === b.lineItemType && a.ordinal === b.ordinal;
export const slotKey = (v: {lineItemType: unknown; ordinal: unknown}) => `${v.lineItemType}:${v.ordinal}`;
export const unique = <T,>(items: T[], key: (v: T) => unknown) => new Set(items.map(key)).size === items.length;
export function requireValue(condition: unknown): asserts condition {
  if (!condition) throw new Error("Line-item authority is unavailable or inconsistent. Reload before making a decision.");
}
export const values = (v: Record<string, unknown>) => ["code", "codeSystem", "description", "unit", "currency", "categoryHint"].every((key) => nullableText(v[key]))
  && (v.serviceDate === null || (text(v.serviceDate) && /^\d{4}-\d{2}-\d{2}$/.test(v.serviceDate) && Number.isFinite(Date.parse(v.serviceDate))))
  && ["quantity", "unitPrice", "grossAmount", "discountAmount", "taxAmount", "netAmount", "allowedAmount", "planPaidAmount"]
    .every((key) => v[key] === null || (text(v[key]) && /^-?\d{1,14}(?:\.\d{1,4})?$/.test(v[key])));
export function evidence(v: unknown): boolean {
  return Array.isArray(v) && v.every((ref) => object(ref) && natural(ref.pageNumber) && ref.pageNumber > 0
    && text(ref.sourceEngine) && !!ref.sourceEngine
    && (ref.sourceText == null || (text(ref.sourceText) && !!ref.sourceText.trim()))
    && (ref.elementId == null || uuid(ref.elementId)) && (ref.tableId == null || uuid(ref.tableId))
    && (ref.rowIndex == null || natural(ref.rowIndex)) && (ref.columnIndex == null || natural(ref.columnIndex))
    && (ref.textSpan == null || (object(ref.textSpan) && natural(ref.textSpan.start) && natural(ref.textSpan.end) && ref.textSpan.end > ref.textSpan.start))
    && (ref.bbox == null || (Array.isArray(ref.bbox) && ref.bbox.length === 4 && ref.bbox.every((n) => typeof n === "number" && Number.isFinite(n))
      && 0 <= ref.bbox[0] && ref.bbox[0] < ref.bbox[2] && ref.bbox[2] <= 1 && 0 <= ref.bbox[1] && ref.bbox[1] < ref.bbox[3] && ref.bbox[3] <= 1))
    && !!(ref.sourceText || ref.elementId || (ref.tableId && ref.rowIndex != null) || ref.textSpan || ref.bbox));
}
