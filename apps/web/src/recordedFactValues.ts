import {formatDate} from "./format";

/** Display the supplied decimal without a float conversion or currency assumption. */
export function exactDecimal(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return "Not recorded";
  if (typeof value === "number" && !Number.isFinite(value)) return "Invalid recorded number";
  const text = String(value);
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(text);
  if (!match) return text;
  return `${match[1]}${match[2].replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${match[3] ? `.${match[3]}` : ""}`;
}

export function recordedValue(value: unknown, valueType?: string, currency?: string | null): string {
  if (valueType === "json" && value !== undefined) return JSON.stringify(value, null, 2);
  if (value === null || value === undefined) return "Not recorded";
  if (valueType === "money" || (typeof value === "object" && "amount" in value)) {
    const money = typeof value === "object" ? value as {amount?: unknown; currency?: unknown} : {amount: value};
    const code = typeof money.currency === "string" && money.currency ? money.currency : currency;
    return `${code || "Currency unspecified"} ${exactDecimal(money.amount)}`;
  }
  if (valueType === "number" || valueType === "integer" || typeof value === "number") return exactDecimal(value);
  if (valueType === "date" && typeof value === "string") return formatDate(value) === "-" ? value : formatDate(value);
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}
