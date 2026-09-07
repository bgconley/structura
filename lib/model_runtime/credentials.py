"""Read model credentials without embedding them in URLs or public profile data."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from pydantic import SecretStr

from lib.model_runtime.http_client import ModelConfigurationError


def model_api_key(secret: SecretStr | None, secret_file: Path | None) -> str | None:
    if secret is not None and secret_file is not None:
        raise ModelConfigurationError("Configure one model credential source.")
    if secret is not None:
        return secret.get_secret_value()
    if secret_file is None:
        return None
    try:
        descriptor = os.open(secret_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                raise ModelConfigurationError("Model credential file must be private and regular.")
            value = stream.read(8193)
        if len(value) > 8192 or not value.strip():
            raise ModelConfigurationError("Model credential file is empty or exceeds its limit.")
        return value.strip()
    except (OSError, UnicodeError):
        raise ModelConfigurationError("Model credential file cannot be read.") from None
