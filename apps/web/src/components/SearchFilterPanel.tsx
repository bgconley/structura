import {familyLabel} from "../format";
import type {Folder, SearchMode, SearchRequest, Tag} from "../types";

const modeOptions: SearchMode[] = ["hybrid", "lexical", "semantic", "visual"];
const familyOptions = [
  "",
  "medical_eob",
  "medical_bill",
  "invoice",
  "receipt",
  "warranty",
  "tax_document",
  "legal_contract",
];
const reviewStatusOptions = [
  "",
  "unreviewed",
  "auto_accepted",
  "needs_review",
  "user_confirmed",
  "user_corrected",
  "rejected",
];
const sensitivityOptions = ["", "normal", "pii", "financial", "medical", "legal", "highly_sensitive"];
const relationshipTypeOptions = [
  "",
  "duplicate_of",
  "related_to",
  "invoice_for",
  "receipt_for",
  "eob_for",
  "bill_for",
  "warranty_for",
  "renewal_of",
];
const deadlineTypeOptions = [
  "",
  "due_date",
  "renewal_date",
  "warranty_expiration",
  "response_deadline",
  "filing_deadline",
  "appointment_date",
];

export type SearchFilterState = {
  mode: SearchMode;
  family: string;
  folderId: string;
  tag: string;
  reviewStatus: string;
  sensitivity: string;
  relationshipType: string;
  hasRelationships: boolean;
  deadlineType: string;
  hasOpenDeadlines: boolean;
  includeVisual: boolean;
  reviewedOnly: boolean;
  dateFrom: string;
  dateTo: string;
  amountMin: string;
  amountMax: string;
};

export const defaultSearchFilterState: SearchFilterState = {
  mode: "hybrid",
  family: "",
  folderId: "",
  tag: "",
  reviewStatus: "",
  sensitivity: "",
  relationshipType: "",
  hasRelationships: false,
  deadlineType: "",
  hasOpenDeadlines: false,
  includeVisual: false,
  reviewedOnly: false,
  dateFrom: "",
  dateTo: "",
  amountMin: "",
  amountMax: "",
};

export function searchRequestFromFilters(
  query: string,
  filters: SearchFilterState,
): SearchRequest {
  return {
    query,
    mode: filters.mode,
    families: filters.family ? [filters.family] : [],
    folderIds: filters.folderId ? [filters.folderId] : [],
    tags: filters.tag ? [filters.tag] : [],
    reviewStatuses: filters.reviewStatus ? [filters.reviewStatus] : [],
    reviewedOnly: filters.reviewedOnly || undefined,
    dateFrom: filters.dateFrom || undefined,
    dateTo: filters.dateTo || undefined,
    amountMin: filters.amountMin ? Number(filters.amountMin) : undefined,
    amountMax: filters.amountMax ? Number(filters.amountMax) : undefined,
    sensitivity: filters.sensitivity ? [filters.sensitivity] : [],
    relationshipTypes: filters.relationshipType ? [filters.relationshipType] : [],
    hasRelationships: filters.hasRelationships || undefined,
    deadlineTypes: filters.deadlineType ? [filters.deadlineType] : [],
    hasOpenDeadlines: filters.hasOpenDeadlines || undefined,
    includeVisual: filters.includeVisual || filters.mode === "visual" || undefined,
    includeDebug: true,
  };
}

export function activeSearchFilters(
  filters: SearchFilterState,
  folders: Folder[],
): string[] {
  const selectedFolder = selectedSearchFolder(filters, folders);
  return [
    filters.family ? familyLabel(filters.family) : null,
    selectedFolder ? `folder ${selectedFolder.path ?? selectedFolder.name}` : null,
    filters.tag ? `tag ${filters.tag}` : null,
    filters.reviewStatus ? `review ${filters.reviewStatus}` : null,
    filters.sensitivity ? `sensitivity ${filters.sensitivity}` : null,
    filters.relationshipType ? `relationship ${filters.relationshipType}` : null,
    filters.hasRelationships ? "has relationships" : null,
    filters.deadlineType ? `deadline ${filters.deadlineType}` : null,
    filters.hasOpenDeadlines ? "open deadlines" : null,
    filters.includeVisual || filters.mode === "visual" ? "visual retrieval" : null,
    filters.reviewedOnly ? "reviewed only" : null,
    filters.dateFrom || filters.dateTo
      ? `${filters.dateFrom || "any"} to ${filters.dateTo || "any"}`
      : null,
    filters.amountMin || filters.amountMax
      ? `$${filters.amountMin || "0"} to ${filters.amountMax || "any"}`
      : null,
  ].filter((value): value is string => Boolean(value));
}

export function selectedSearchFolder(
  filters: SearchFilterState,
  folders: Folder[],
): Folder | undefined {
  return folders.find((folder) => folder.id === filters.folderId);
}

export function SearchFilterPanel({
  filters,
  folders,
  tags,
  onChange,
}: {
  filters: SearchFilterState;
  folders: Folder[];
  tags: Tag[];
  onChange: (filters: SearchFilterState) => void;
}) {
  const selectedFolder = selectedSearchFolder(filters, folders);

  function updateFilter<K extends keyof SearchFilterState>(
    key: K,
    value: SearchFilterState[K],
  ) {
    onChange({...filters, [key]: value});
  }

  return (
    <aside className="search-filter-panel">
      <h2>Filters</h2>
      <label>
        Search mode
        <select
          aria-label="Search mode"
          value={filters.mode}
          onChange={(event) => updateFilter("mode", event.target.value as SearchMode)}
        >
          {modeOptions.map((option) => <option key={option}>{option}</option>)}
        </select>
      </label>
      <label>
        Document family filter
        <select
          aria-label="Document family filter"
          value={filters.family}
          onChange={(event) => updateFilter("family", event.target.value)}
        >
          {familyOptions.map((option) => (
            <option key={option} value={option}>{option ? familyLabel(option) : "Any family"}</option>
          ))}
        </select>
      </label>
      <label>
        Folder filter
        <select
          aria-label="Folder filter"
          value={filters.folderId}
          onChange={(event) => updateFilter("folderId", event.target.value)}
        >
          <option value="">Any folder</option>
          {folders.map((folder) => (
            <option key={folder.id} value={folder.id}>
              {folder.path ?? folder.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tag filter
        <select
          aria-label="Tag filter"
          value={filters.tag}
          onChange={(event) => updateFilter("tag", event.target.value)}
        >
          <option value="">Any tag</option>
          {tags.map((item) => (
            <option key={item.id} value={item.name}>{item.name}</option>
          ))}
        </select>
      </label>
      <label>
        Review status filter
        <select
          aria-label="Review status filter"
          value={filters.reviewStatus}
          onChange={(event) => updateFilter("reviewStatus", event.target.value)}
        >
          {reviewStatusOptions.map((option) => (
            <option key={option} value={option}>{option || "Any review status"}</option>
          ))}
        </select>
      </label>
      <label>
        Sensitivity filter
        <select
          aria-label="Sensitivity filter"
          value={filters.sensitivity}
          onChange={(event) => updateFilter("sensitivity", event.target.value)}
        >
          {sensitivityOptions.map((option) => (
            <option key={option} value={option}>{option || "Any sensitivity"}</option>
          ))}
        </select>
      </label>
      <label>
        Relationship filter
        <select
          aria-label="Relationship filter"
          value={filters.relationshipType}
          onChange={(event) => updateFilter("relationshipType", event.target.value)}
        >
          {relationshipTypeOptions.map((option) => (
            <option key={option} value={option}>{option || "Any relationship"}</option>
          ))}
        </select>
      </label>
      <label>
        Deadline filter
        <select
          aria-label="Deadline filter"
          value={filters.deadlineType}
          onChange={(event) => updateFilter("deadlineType", event.target.value)}
        >
          {deadlineTypeOptions.map((option) => (
            <option key={option} value={option}>{option || "Any deadline"}</option>
          ))}
        </select>
      </label>
      <label>
        Date from
        <input
          value={filters.dateFrom}
          onChange={(event) => updateFilter("dateFrom", event.target.value)}
          type="date"
        />
      </label>
      <label>
        Date to
        <input
          value={filters.dateTo}
          onChange={(event) => updateFilter("dateTo", event.target.value)}
          type="date"
        />
      </label>
      <label>
        Amount minimum
        <input
          aria-label="Amount minimum"
          value={filters.amountMin}
          onChange={(event) => updateFilter("amountMin", event.target.value)}
          min="0"
          step="0.01"
          type="number"
        />
      </label>
      <label>
        Amount maximum
        <input
          aria-label="Amount maximum"
          value={filters.amountMax}
          onChange={(event) => updateFilter("amountMax", event.target.value)}
          min="0"
          step="0.01"
          type="number"
        />
      </label>
      <label className="filter-check">
        <input
          checked={filters.reviewedOnly}
          onChange={(event) => updateFilter("reviewedOnly", event.target.checked)}
          type="checkbox"
        />
        Reviewed only
      </label>
      <label className="filter-check">
        <input
          checked={filters.hasRelationships}
          onChange={(event) => updateFilter("hasRelationships", event.target.checked)}
          type="checkbox"
        />
        Has relationships
      </label>
      <label className="filter-check">
        <input
          checked={filters.hasOpenDeadlines}
          onChange={(event) => updateFilter("hasOpenDeadlines", event.target.checked)}
          type="checkbox"
        />
        Has open deadlines
      </label>
      <label className="filter-check">
        <input
          checked={filters.includeVisual}
          onChange={(event) => updateFilter("includeVisual", event.target.checked)}
          type="checkbox"
        />
        Include visual matches
      </label>
      <div className="filter-chip-list">
        <span className={filters.family ? "selected" : undefined}>
          Family: {filters.family || "Any"}
        </span>
        <span className={filters.folderId ? "selected" : undefined}>
          Folder: {selectedFolder?.name ?? "Any"}
        </span>
        <span className={filters.tag ? "selected" : undefined}>Tag: {filters.tag || "Any"}</span>
        <span className={filters.reviewStatus ? "selected" : undefined}>
          Review status: {filters.reviewStatus || "Any"}
        </span>
        <span className={filters.sensitivity ? "selected" : undefined}>
          Sensitivity: {filters.sensitivity || "Any"}
        </span>
        <span className={filters.relationshipType ? "selected" : undefined}>
          Relationship: {filters.relationshipType || "Any"}
        </span>
        <span className={filters.deadlineType ? "selected" : undefined}>
          Deadline: {filters.deadlineType || "Any"}
        </span>
        <span>Date: {filters.dateFrom || "any"} - {filters.dateTo || "any"}</span>
        <span>Amount: {filters.amountMin || "0"} - {filters.amountMax || "any"}</span>
        <span>Review: {filters.reviewedOnly ? "Reviewed" : "Any"}</span>
        <span>Links: {filters.hasRelationships ? "Required" : "Any"}</span>
        <span>Deadlines: {filters.hasOpenDeadlines ? "Open only" : "Any"}</span>
        <span>Visual: {filters.includeVisual || filters.mode === "visual" ? "On" : "Off"}</span>
      </div>
    </aside>
  );
}
