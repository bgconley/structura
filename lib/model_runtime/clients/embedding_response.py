"""Strict vector, response-index and reported-model validation."""

from __future__ import annotations

import math
from typing import Any

from lib.model_runtime.http_client import ModelConfigurationError, ModelProtocolError
from lib.model_runtime.profiles import ModelProfile


def response_vectors(
    response: dict[str, Any] | list[Any], *, profile: ModelProfile, count: int
) -> tuple[tuple[tuple[float, ...], ...], str, str]:
    protocol = profile.embedding_protocol
    if protocol is None or profile.output_dimensions is None:
        raise ModelConfigurationError("Embedding profile must declare its protocol and dimensions.")
    expected_model = profile.served_model_name or profile.base_model
    if protocol.api_flavor == "tei":
        if not isinstance(response, list) or len(response) != count:
            raise ModelProtocolError("TEI embedding response vector count does not match request.")
        # TEI's native array cannot attest model identity. The response explicitly
        # records deployment_pinned provenance; it never claims a reported model.
        return (
            tuple(
                validated_vector(item, dimensions=profile.output_dimensions) for item in response
            ),
            expected_model,
            "",
        )
    if not isinstance(response, dict) or response.get("model") != expected_model:
        raise ModelProtocolError("Embedding response model does not match the declared profile.")
    version = response.get("model_version", "")
    if not isinstance(version, str):
        raise ModelProtocolError("Embedding response model version is invalid.")
    data = response.get("data")
    if not isinstance(data, list) or len(data) != count:
        raise ModelProtocolError("Embedding response vector count does not match request count.")
    indexed: dict[int, tuple[float, ...]] = {}
    for item in data:
        if not isinstance(item, dict):
            raise ModelProtocolError("Embedding response item is invalid.")
        index = item.get("index")
        if type(index) is not int or index < 0 or index >= count or index in indexed:
            raise ModelProtocolError("Embedding response indexes do not match request inputs.")
        indexed[index] = validated_vector(
            item.get("embedding"), dimensions=profile.output_dimensions
        )
    return tuple(indexed[index] for index in range(count)), expected_model, version


def validated_vector(values: object, *, dimensions: int) -> tuple[float, ...]:
    if not isinstance(values, list | tuple) or len(values) != dimensions:
        raise ModelProtocolError("Embedding response dimension does not match profile.")
    if any(type(value) not in {int, float} for value in values):
        raise ModelProtocolError("Embedding response vector must contain numbers.")
    try:
        vector = tuple(float(value) for value in values)
    except (OverflowError, ValueError):
        raise ModelProtocolError("Embedding response vector contains invalid numbers.") from None
    if not all(math.isfinite(value) for value in vector):
        raise ModelProtocolError("Embedding response contains non-finite values.")
    if any(abs(value) > 3.4028234663852886e38 for value in vector):
        raise ModelProtocolError("Embedding response exceeds the index numeric range.")
    if not any(abs(value) >= 1.401298464324817e-45 for value in vector):
        raise ModelProtocolError("Embedding response vector must have nonzero magnitude.")
    return vector
