"""Extractive-first text lane (ADR 0006).

Values in this lane are copied verbatim from Docling structure (table cell
grids, elements, spans) and parsed deterministically; models only select
(column roles, span ids) through closed enum micro-schemas and never emit a
value. The vision path remains the exception lane for scans, handwriting,
degraded text layers, and text-lane abstentions.
"""
