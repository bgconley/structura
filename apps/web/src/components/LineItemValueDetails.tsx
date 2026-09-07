import {recordedValue} from "../recordedFactValues";
import type {LineValues} from "../lineItems/types";

export function LineItemValueDetails({value, family}: {value: LineValues; family?: string}) {
  const eob = family === "medical_eob" || family?.startsWith("medical_eob.");
  const fields = [
    ["code", "Code", "string"], ["codeSystem", "Code system", "string"], ["serviceDate", "Service date", "date"],
    ["quantity", "Quantity", "number"], ["unit", "Unit", "string"], ["unitPrice", "Unit price", "money"],
    ["grossAmount", eob ? "Billed" : "Gross amount", "money"], ["allowedAmount", "Allowed", "money"],
    ["planPaidAmount", "Plan paid", "money"], ["discountAmount", "Discount", "money"], ["taxAmount", "Tax", "money"],
    ["netAmount", eob ? "Patient responsibility" : "Net amount", "money"], ["categoryHint", "Category", "string"],
  ] as const;
  return <dl className="line-value-details">{fields.map(([key, label, type]) => <div key={key}>
    <dt>{label}</dt><dd>{recordedValue(value[key], type, value.currency)}</dd>
  </div>)}</dl>;
}
