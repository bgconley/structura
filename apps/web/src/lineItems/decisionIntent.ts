import type {CanonicalLine, CanonicalLines, ExistingTarget, LineCandidate, LineRequest, SourceExpectation} from "./types";

export function sourceExpectation(candidate: LineCandidate): SourceExpectation {
  return {candidateId: candidate.id, expectedCandidateVersion: candidate.candidateVersion,
    expectedSourceSnapshotSha256: candidate.sourceSnapshotSha256, expectedCandidateDecisionRevision: candidate.candidateDecisionRevision};
}
export function existingTarget(item: CanonicalLine, authority: CanonicalLines): ExistingTarget {
  if (!authority.items.includes(item)) throw new Error("Reload the recorded line before choosing it.");
  return {canonicalLineItemId: item.id, lineItemType: item.lineItemType, ordinal: item.ordinal, expectedCanonicalUpdatedAt: item.updatedAt,
    expectedLineDecisionRevision: authority.decisions.find((decision) => decision.canonicalLineItemId === item.id)?.revision ?? null};
}
export function lineLabel(item: Pick<CanonicalLine, "description" | "lineItemType" | "ordinal">) {
  return `${item.description || item.lineItemType.replaceAll("_", " ")} · recorded line ${item.ordinal}`;
}
export function canReplace(candidate: LineCandidate, item: CanonicalLine) {
  return candidate.publicationEligibility.eligible && !candidate.sourceAssignment?.currentlySelected
    && candidate.lineItemType === item.lineItemType && (!candidate.sourceAssignment
      || (candidate.sourceAssignment.state === "assigned" && candidate.sourceAssignment.canonicalLineItemId === item.id));
}
export function requestStillMatches(request: LineRequest, candidate: LineCandidate | null, authority: CanonicalLines) {
  if ("source" in request && (!candidate || JSON.stringify(sourceExpectation(candidate)) !== JSON.stringify(request.source))) return false;
  if (request.operation === "create") return !!candidate?.publicationEligibility.eligible && candidate.sourceAssignment === null
    && !authority.items.some((item) => item.lineItemType === request.target.lineItemType && item.ordinal === request.target.ordinal);
  if ("target" in request) {
    const item = authority.items.find((line) => line.id === request.target.canonicalLineItemId);
    if (!item || JSON.stringify(existingTarget(item, authority)) !== JSON.stringify(request.target)) return false;
    return request.operation === "reject_selected" ? item.selected : !!candidate && canReplace(candidate, item);
  }
  return !candidate?.sourceAssignment?.currentlySelected;
}
