export function familyLabel(family: string): string {
  return family.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatDate(value?: string): string {
  if (!value) {
    return "-";
  }
  const calendarDate = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const parsed = new Date(calendarDate ? `${value}T00:00:00Z` : value);
  if (!Number.isFinite(parsed.getTime()) || (calendarDate
    && (value.startsWith("0000") || parsed.toISOString().slice(0, 10) !== value))) {
    return "-";
  }
  // A source calendar date is not an instant. Formatting it in the user's
  // zone would move UTC midnight into the prior day west of Greenwich.
  return new Intl.DateTimeFormat(undefined, {
    month: "short", day: "numeric", year: "numeric",
    ...(calendarDate ? {timeZone: "UTC"} : {}),
  }).format(parsed);
}

export function formatAmount(value?: number): string {
  if (typeof value !== "number") {
    return "-";
  }
  return new Intl.NumberFormat(undefined, {style: "currency", currency: "USD"}).format(value);
}
