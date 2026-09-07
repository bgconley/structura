"""Static persisted content rejection codes, never runtime/source diagnostics."""

from lib.uploads.errors import ERROR_DETAILS

MESSAGES = {
    key: ERROR_DETAILS[key][1]
    for key in (
        "upload_size_mismatch",
        "upload_signature_unsupported",
        "upload_format_mismatch",
        "upload_too_large",
    )
}
