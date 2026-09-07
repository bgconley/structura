import type {Page} from "@playwright/test";
import type {CanonicalField, FieldDecision} from "../../../apps/web/src/types";
import type {RecordedLineItem} from "../../../apps/web/src/recordedLineItems";
import {existingDocument, seededDocuments} from "./structuraFixtures";
import {reviewAuthorityFixture} from "./reviewAuthorityFixture";

const id = (value: number) => `aaaaaaaa-aaaa-4aaa-8aaa-${String(value).padStart(12, "0")}`;
export function viewerFactsData() {
  const document = structuredClone(seededDocuments().get(existingDocument.id)!);
  document.family = "invoice";
  document.pages = [1, 2, 3].map((pageNumber) => ({pageNumber, imageUrl: document.pages[0].imageUrl}));
  document.fields = [{id: id(99), fieldPath: "untrusted.detail.only", value: "Must not appear as accepted", reviewStatus: "auto_accepted"}];
  const fields: CanonicalField[] = Array.from({length: 14}, (_, index) => ({id: id(index + 1), documentId: document.id,
    fieldPath: `invoice.field_${String(index + 1).padStart(2, "0")}`, ordinal: 1, valueType: "money",
    value: {amount: index === 13 ? "99999999999999.9999" : "1.2345", currency: "EUR"}, sourceKind: "human",
    reviewStatus: "user_corrected", updatedAt: "2026-09-07T10:11:12.123456Z",
    evidence: [{pageNumber: index === 13 ? 3 : 1, sourceEngine: "human", textSpan: {start: index, end: index + 1},
      sourceText: `Source for field ${index + 1}`}]}));
  fields[0] = {...fields[0], valueType: "date", value: "2026-01-26"};
  fields[1] = {...fields[1], valueType: "json", value: {terms: ["First term", "Second term"], cleared: null}};
  fields[2] = {...fields[2], valueType: "boolean", value: false};
  fields[3] = {...fields[3], valueType: "number", value: "-12.3400"};
  fields[4] = {...fields[4], value: {amount: "0.0000", currency: "JPY"}};
  fields[5] = {...fields[5], valueType: "datetime", value: "2026-09-07T10:11:12.123456-04:00"};
  fields[7] = {...fields[7], valueType: "integer", value: "9223372036854775807"};
  const decisions: FieldDecision[] = [{id: id(100), documentId: document.id, fieldPath: fields[6].fieldPath,
    ordinal: 1, revision: id(101), disposition: "rejected", origin: "live_review", canonicalFieldId: fields[6].id,
    reviewEventId: null, actorUserId: null, decidedAt: "2026-09-07T10:11:12Z", recordedAt: "2026-09-07T10:11:12Z"},
  {id: id(102), documentId: document.id, fieldPath: "invoice.deleted_value", ordinal: 2, revision: id(103),
    disposition: "rejected", origin: "live_review", canonicalFieldId: null, reviewEventId: null, actorUserId: null,
    decidedAt: "2026-09-07T10:11:12Z", recordedAt: "2026-09-07T10:11:12Z"}];
  const lines: RecordedLineItem[] = Array.from({length: 25}, (_, index) => ({id: id(200 + index), documentId: document.id,
    lineItemType: "service_line", ordinal: index + 1, description: `Recorded service ${index + 1}`, code: "99213", codeSystem: "CPT",
    serviceDate: "2026-01-26", quantity: "1.2345", unit: "hour", unitPrice: "0.0000", grossAmount: "99999999999999.9999",
    discountAmount: "-12.3400", taxAmount: null, netAmount: "120.0100", currency: "EUR", sourceKind: "human",
    reviewStatus: index === 24 ? "rejected" : "user_confirmed", validation: {warnings: ["Retained validation"]},
    evidence: [{pageNumber: index >= 20 ? 3 : 1, tableId: id(500), rowIndex: index, sourceEngine: "human",
      sourceText: `Source for service ${index + 1}`}]}));
  document.lineItems = lines;
  return {document, fields, lines, authority: reviewAuthorityFixture(document.id, fields, decisions)};
}

export async function mockViewerFacts(page: Page, data = viewerFactsData()) {
  await page.route(`**/api/v1/documents/${data.document.id}`, (route) => route.fulfill({json: data.document}));
  await page.route(`**/api/v1/documents/${data.document.id}/canonical-fields`, (route) => route.fulfill({json: data.authority}));
  return data;
}
