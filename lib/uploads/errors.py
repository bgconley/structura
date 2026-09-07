"""Static public upload failures; never retain request or filesystem content."""

ERROR_DETAILS = {
    "upload_conflict": (409, "Upload revision or content conflicts."),
    "upload_unavailable": (404, "Upload unavailable."),
    "upload_capacity": (429, "Upload capacity is temporarily occupied."),
    "upload_storage_unavailable": (503, "Upload storage is unavailable."),
    "upload_service_unavailable": (503, "Upload service is unavailable."),
    "upload_timed_out": (408, "Upload transfer timed out."),
    "upload_too_large": (413, "Upload exceeds the file limit."),
    "upload_control_too_large": (413, "Upload control body is too large."),
    "upload_size_mismatch": (422, "Uploaded byte count does not match."),
    "upload_signature_unsupported": (415, "File signature is unsupported."),
    "upload_format_mismatch": (415, "File signature and metadata disagree."),
}


class UploadError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code if code in ERROR_DETAILS else "upload_service_unavailable"
        self.status_code, message = ERROR_DETAILS[self.code]
        super().__init__(message)


class UploadConflict(UploadError):
    def __init__(self) -> None:
        super().__init__("upload_conflict")


class UploadUnavailable(UploadError):
    def __init__(self) -> None:
        super().__init__("upload_unavailable")


class UploadCapacity(UploadError):
    def __init__(self) -> None:
        super().__init__("upload_capacity")


class UploadStorageUnavailable(UploadError):
    def __init__(self) -> None:
        super().__init__("upload_storage_unavailable")
