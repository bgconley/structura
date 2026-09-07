"""Reuse the isolated candidate-storage harness without altering its source fixtures."""

from tests.integration.document_processing.conftest import processing as processing

__all__ = ["processing"]
