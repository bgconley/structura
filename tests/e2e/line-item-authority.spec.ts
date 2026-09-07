import {expect, test} from "@playwright/test";
import {parseCandidateLines, parseCanonicalLines, parseLineResult} from "../../apps/web/src/lineItems/authority";
import {parseLineHistory} from "../../apps/web/src/lineItems/historyAuthority";
import {existingTarget, requestStillMatches, sourceExpectation} from "../../apps/web/src/lineItems/decisionIntent";
import {canonicalLine, canonicalLines, lineCandidate, lineHistoryEntry, lineId, lineSourceSnapshot} from "./support/lineItemAuthorityMock";

const documentId = lineId(999);
test("line authority preserves zero, negative, four-place and maximum exact money", () => {
  const source = lineCandidate(documentId), authority = canonicalLines(documentId, [canonicalLine(documentId)]);
  const candidates = parseCandidateLines({authorityVersion: "line_item_authority.v1", documentId, items: [source]}, documentId, source.id);
  expect(candidates.items[0].grossAmount).toBe("99999999999999.9999");
  expect(candidates.items[0].unitPrice).toBe("0.0000");
  expect(candidates.items[0].discountAmount).toBe("-12.3400");
  expect(parseCanonicalLines(authority, documentId).items[0].allowedAmount).toBe("220.1234");
});
for (const malformed of ["missing envelope", "foreign item", "orphan decision", "wrong slot", "selected rejection", "duplicate row", "numeric rounding", "missing basis", "live event absent"]) {
  test(`canonical mutation fails closed: ${malformed}`, () => {
    const value: any = canonicalLines(documentId, [canonicalLine(documentId)]);
    if (malformed === "missing envelope") delete value.authorityVersion;
    if (malformed === "foreign item") value.items[0].documentId = lineId(998);
    if (malformed === "orphan decision") value.decisions[0].canonicalLineItemId = lineId(997);
    if (malformed === "wrong slot") value.decisions[0].ordinal = 2;
    if (malformed === "selected rejection") value.decisions[0].disposition = "rejected";
    if (malformed === "duplicate row") value.items.push({...value.items[0]});
    if (malformed === "numeric rounding") value.items[0].grossAmount = 99999999999999.9999;
    if (malformed === "missing basis") delete value.projection.acceptedFactBasisSchemaVersion;
    if (malformed === "live event absent") value.decisions[0].decisionEventId = null;
    expect(() => parseCanonicalLines(value, documentId)).toThrow(/unavailable or inconsistent/);
  });
}
test("a proposal's permanent assignment cannot silently move or create another row", () => {
  const source = lineCandidate(documentId), authority = canonicalLines(documentId, [canonicalLine(documentId), canonicalLine(documentId, 2)]);
  source.sourceAssignment = {sourceCandidateId: source.id, state: "assigned", canonicalLineItemId: authority.items[0].id,
    target: {lineItemType: "service_line", ordinal: 1}, currentlySelected: false};
  expect(requestStillMatches({operation: "replace", source: sourceExpectation(source), target: existingTarget(authority.items[1], authority)}, source, authority)).toBe(false);
  expect(requestStillMatches({operation: "create", source: sourceExpectation(source), target: source.suggestedVacantTarget!}, source, authority)).toBe(false);
  expect(requestStillMatches({operation: "replace", source: sourceExpectation(source), target: existingTarget(authority.items[0], authority)}, source, authority)).toBe(true);
});
test("source and target revisions invalidate an already reviewed intention", () => {
  const source = lineCandidate(documentId), authority = canonicalLines(documentId, [canonicalLine(documentId)]);
  const request = {operation: "replace" as const, source: sourceExpectation(source), target: existingTarget(authority.items[0], authority)};
  expect(requestStillMatches(request, source, authority)).toBe(true);
  expect(requestStillMatches(request, {...source, candidateVersion: lineId(222)}, authority)).toBe(false);
  authority.decisions[0].revision = lineId(223);
  expect(requestStillMatches(request, source, authority)).toBe(false);
});
test("history requires exact selection identity and never upgrades partial legacy coverage", () => {
  const item = canonicalLine(documentId), entry = lineHistoryEntry(item);
  const history = {documentId, items: [entry], nextCursor: null};
  expect(parseLineHistory(history, documentId, {canonicalLineItemId: item.id}).items[0].after?.sourceCoverage).toBe("legacy_unestablished");
  expect(() => parseLineHistory(history, documentId, {canonicalLineItemId: lineId(888)})).toThrow();
  expect(() => parseLineHistory({...history, items: [{...entry, documentId: lineId(887)}]}, documentId, {canonicalLineItemId: item.id})).toThrow();
});
test("candidate extraction identity and unusable evidence cannot authorize publication", () => {
  const source = lineCandidate(documentId);
  const parse = (item: unknown) => parseCandidateLines({authorityVersion: "line_item_authority.v1", documentId, items: [item]}, documentId);
  expect(() => parse({...source, extraction: {...source.extraction, documentId: lineId(887)}})).toThrow();
  expect(() => parse({...source, evidence: [{pageNumber: 1, sourceEngine: "human", sourceText: ""}]})).toThrow();
  expect(() => parse({...source, evidence: [{pageNumber: 1, sourceEngine: "human", bbox: [1, 1, 0, 0]}]})).toThrow();
});

for (const operation of ["create", "replace", "reject_selected", "reject_candidate"]) {
  test(`complete ${operation} history cannot omit its operation snapshots`, () => {
    const item = canonicalLine(documentId), entry = {...lineHistoryEntry(item), operation, before: null, after: null, source: null};
    expect(() => parseLineHistory({documentId, items: [entry], nextCursor: null}, documentId, {canonicalLineItemId: item.id})).toThrow();
  });
}
test("retained history binds each source to its selected row while allowing a deleted source foreign key", () => {
  const candidate = lineCandidate(documentId), source = lineSourceSnapshot(candidate);
  const item = {...canonicalLine(documentId), selectedCandidateId: candidate.id};
  const value = {canonical: item, source, sourceCoverage: "recorded" as const};
  const entry = {...lineHistoryEntry(item), operation: "replace", sourceCandidateId: candidate.id, source, before: value, after: value};
  const parse = (historyEntry: unknown) => parseLineHistory({documentId, items: [historyEntry], nextCursor: null}, documentId, {canonicalLineItemId: item.id});
  expect(parse(entry).items[0].after?.source?.candidate.id).toBe(candidate.id);
  for (const side of ["before", "after"]) {
    expect(() => parse({...entry, [side]: {...value, canonical: {...item, selectedCandidateId: lineId(887)}}})).toThrow();
  }
  const retained = {...value, canonical: {...item, selectedCandidateId: null}};
  expect(parse({...entry, before: retained, after: retained}).items[0].after?.source?.candidate.id).toBe(candidate.id);
  expect(parse({...entry, operation: "create", before: null, after: retained}).items[0].after?.source?.candidate.id).toBe(candidate.id);
});
test("success from a different target is treated as an unconfirmed save, not accepted locally", () => {
  const source = lineCandidate(documentId), authority = canonicalLines(documentId, [canonicalLine(documentId)]);
  const request = {operation: "replace" as const, source: sourceExpectation(source), target: existingTarget(authority.items[0], authority)};
  expect(() => parseLineResult({operation: "replace", eventId: lineId(600), canonicalItem: canonicalLine(documentId, 2),
    lineDecision: authority.decisions[0], candidateDecision: null, projection: authority.projection}, documentId, request)).toThrow();
});

test("withdrawal history requires a selected before value and unselected after value", () => {
  const item = canonicalLine(documentId), entry = lineHistoryEntry(item);
  const parse = (value: unknown) => parseLineHistory({documentId, items: [value], nextCursor: null}, documentId, {canonicalLineItemId: item.id});
  expect(parse(entry).items).toHaveLength(1);
  expect(() => parse({...entry, before: {...entry.before, canonical: {...item, selected: false}}})).toThrow();
  expect(() => parse({...entry, after: {...entry.after, canonical: {...item, selected: true}}})).toThrow();
});
