import type {FieldCandidate} from "../types";

export function CorrectionValueInput({candidate, disabled, error}: {
  candidate?: FieldCandidate;
  disabled: boolean;
  error: string | null;
}) {
  const valueType = candidate?.valueType;
  const shared = {
    name: "correctedValue",
    "aria-label": "Corrected value",
    "aria-invalid": error ? true as const : undefined,
    "aria-describedby": error ? "correction-error" : "correction-input-help",
    disabled,
    required: true,
  };
  const hint = valueType === "datetime"
    ? "Include seconds and an explicit UTC offset or Z; local time alone is ambiguous."
    : valueType === "json"
      ? "Enter JSON: object, array, quoted text, number, boolean or null."
      : valueType === "date" ? "Choose a calendar date."
        : valueType === "money" || valueType === "number"
          ? "Use a decimal amount such as 1234.56, without currency or grouping separators."
          : valueType === "boolean" ? "Choose true or false."
            : "Enter the corrected value shown by the source evidence.";
  return <>
    <label>
      Corrected value
      {valueType === "json" ? <textarea {...shared} rows={4} placeholder={'{"paid": false}'} />
        : valueType === "boolean" ? <select {...shared} defaultValue="">
          <option value="" disabled>Choose a value</option>
          <option value="true">True</option><option value="false">False</option>
        </select>
          : <input {...shared} type={valueType === "date" ? "date" : "text"}
            inputMode={valueType === "money" || valueType === "number" ? "decimal" : "text"}
            placeholder={valueType === "datetime" ? "2026-09-07T14:30:00-04:00" : undefined} />}
    </label>
    <small id="correction-input-help">{hint}</small>
  </>;
}
