"""Text-lane extraction gateway (ADR 0006 X2, migration phase E1).

Produces the same GatewayExtraction/RegionExtractionEnvelope persistence
shape as the vision path so reconciliation, candidates, the resolver,
invariants, and review are untouched. Raises TextLaneAbstention when the
region cannot be extracted from Docling structure; the routing gateway then
falls back to the vision path with the abstention recorded as lane telemetry.
"""

from __future__ import annotations

from lib.extraction.contract_registry import resolved_document_type_from_task_metadata
from lib.extraction.model_output_value_parsing import parse_decimal_text
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction, ModelRoute
from lib.extraction.region_envelope import (
    REGION_ENVELOPE_VERSION,
    envelope_json,
    to_normalization_projection,
)
from lib.extraction.text_lane.column_labeling import (
    ColumnLabelingValidationError,
    ColumnRoleLabeler,
    LiveColumnRoleLabeler,
    line_item_roles,
)
from lib.extraction.text_lane.eligibility import LaneDecision
from lib.extraction.text_lane.table_extractor import (
    MONEY_ROLES,
    TEXT_LANE_TABLE_METHOD,
    extract_table_region,
)
from lib.extraction.text_lane.table_grid import TableGrid
from lib.model_runtime.http_client import ModelProtocolError
from lib.semantic_annotations.models import SemanticExtractionTask


class TextLaneAbstention(Exception):
    """The text lane declined this region; the vision path should run."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TextLaneTableExtractionGateway:
    prompt_version = TEXT_LANE_TABLE_METHOD

    def __init__(self, *, labeler: ColumnRoleLabeler | None = None) -> None:
        self.labeler = labeler or LiveColumnRoleLabeler()

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
        lane_decision: LaneDecision | None = None,
    ) -> GatewayExtraction:
        if semantic_task is None:
            raise TextLaneAbstention("no_semantic_task")
        grid = self._grounded_grid(source, semantic_task)
        family = resolved_document_type_from_task_metadata(
            metadata=semantic_task.metadata,
            semantic_type=semantic_task.semantic_type,
            target_schema=schema_name,
        )
        if not line_item_roles(family):
            raise TextLaneAbstention(f"family_without_line_item_registry:{family}")
        try:
            labeling = self.labeler.label_columns(family=family, grid=grid)
        except (ColumnLabelingValidationError, ModelProtocolError) as exc:
            raise TextLaneAbstention(f"column_labeling_failed:{exc}") from exc
        labeled_roles = {index: role for index, role in labeling.roles.items() if role != "ignore"}
        if not labeled_roles:
            raise TextLaneAbstention("all_columns_labeled_ignore")
        if "description" not in labeled_roles.values():
            raise TextLaneAbstention("no_description_column")
        money_columns = [index for index, role in labeled_roles.items() if role in MONEY_ROLES]
        if not money_columns:
            raise TextLaneAbstention("no_money_column")
        # Docling can lose cell text the page image still shows (weak scans,
        # span misalignment). If most data rows have no parseable money cell,
        # the verbatim lane would silently under-extract values the vision
        # path reads from pixels - abstain instead.
        populated = sum(
            1
            for row_index in grid.data_row_indexes
            if _row_has_parseable_money(grid, row_index, money_columns)
        )
        if populated * 2 < len(grid.data_row_indexes):
            raise TextLaneAbstention("money_columns_sparse")
        extraction = extract_table_region(
            source=source,
            semantic_task=semantic_task,
            grid=grid,
            labeling=labeling,
            family=family,
            target_schema=schema_name,
        )
        if extraction.line_item_count == 0 and extraction.totals_fact_count == 0:
            raise TextLaneAbstention("no_extractable_rows")
        envelope = extraction.envelope
        normalization_json: dict[str, object] = {
            "mapper": TEXT_LANE_TABLE_METHOD,
            "repairs": [],
            "lane": "text",
            "laneEligibility": lane_decision.reason if lane_decision is not None else None,
            "columnRoles": labeling.roles_json(),
            "regionEnvelopeVersion": REGION_ENVELOPE_VERSION,
            "regionEnvelope": envelope_json(envelope),
            "normalizedProjectionDerivedFromEnvelope": True,
        }
        raw_output_json: dict[str, object] = {
            "modelInvoked": not labeling.from_cache,
            "lane": "text",
            "sourceEngine": "docling",
            "columnLabeling": {
                "promptVersion": labeling.prompt_version,
                "modelName": labeling.model_name,
                "modelVersion": labeling.model_version,
                "fromCache": labeling.from_cache,
                "columnRoles": labeling.roles_json(),
            },
            "tableId": grid.table_id,
            "pageNumber": grid.page_number,
            "headerFingerprint": grid.header_fingerprint(),
            "lineItemCount": extraction.line_item_count,
            "totalsFactCount": extraction.totals_fact_count,
            "skippedRowCount": extraction.skipped_row_count,
        }
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=ModelRoute(
                source_engine="docling",
                model_name="text-lane-table-extractor",
                model_version="e1-v1",
                prompt_version=TEXT_LANE_TABLE_METHOD,
                route_profile=route_profile,
            ),
            normalized_json=to_normalization_projection(envelope),
            raw_output_json=raw_output_json,
            model_output_schema_name=TEXT_LANE_TABLE_METHOD,
            model_output_schema_version="v1",
            normalization_json=normalization_json,
            metadata={
                "lane": "text",
                "columnLabelingFromCache": labeling.from_cache,
            },
        )

    def _grounded_grid(
        self,
        source: ExtractionSourceDocument,
        semantic_task: SemanticExtractionTask,
    ) -> TableGrid:
        grounding = semantic_task.grounding
        table = None
        if grounding.table_id is not None:
            table = next(
                (item for item in source.tables if item.table_id == grounding.table_id),
                None,
            )
        if table is None and grounding.element_id is not None:
            table = next(
                (item for item in source.tables if item.element_id == grounding.element_id),
                None,
            )
        if table is None:
            raise TextLaneAbstention("no_grounded_docling_table")
        grid = TableGrid.from_parsed_table(table)
        if grid is None:
            raise TextLaneAbstention("table_grid_missing")
        if not grid.data_row_indexes:
            raise TextLaneAbstention("table_grid_has_no_data_rows")
        return grid


def _row_has_parseable_money(
    grid: TableGrid,
    row_index: int,
    money_columns: list[int],
) -> bool:
    cells = grid.row_cells(row_index)
    for column_index in money_columns:
        cell = cells[column_index] if column_index < len(cells) else None
        if cell is None or not cell.normalized_text:
            continue
        if parse_decimal_text(cell.normalized_text) is not None:
            return True
    return False
