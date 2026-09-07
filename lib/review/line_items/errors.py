class LineDecisionConflict(Exception):
    """A source or target changed; reload exact authority before deciding again."""


class LineEvidenceError(Exception):
    """The proposal does not have complete same-document source evidence."""
