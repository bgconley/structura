"""Content-free retained evidence failures."""


class EvidenceError(Exception):
    pass


class EvidenceUnavailable(EvidenceError):
    pass


class EvidenceConflict(EvidenceError):
    pass
