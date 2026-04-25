export function familyLabel(family: string): string {
  return family.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatDate(value?: string): string {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat(undefined, {month: "short", day: "numeric", year: "numeric"}).format(
    new Date(value),
  );
}

export function formatAmount(value?: number): string {
  if (typeof value !== "number") {
    return "-";
  }
  return new Intl.NumberFormat(undefined, {style: "currency", currency: "USD"}).format(value);
}
