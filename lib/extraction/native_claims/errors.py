from lib.document_processing.errors import ProcessingError


class NativeClaimError(ProcessingError):
    """Static native claim contract failure, without source content."""


class NativeClaimConflict(NativeClaimError):
    """An immutable source/claim identity was replayed with changed content."""
