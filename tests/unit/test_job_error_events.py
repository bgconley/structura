from __future__ import annotations

import json
from uuid import UUID, uuid4

from lib.jobs.operator_repository import cancel_job_row as _cancel_job_row
from lib.jobs.public_errors import public_job_error, safe_job_failure
from lib.jobs.recovery_repository import recover_expired_job

PRIVATE = "patient source text /private/document.pdf token=secret"


class Cursor:
    rowcount = 1

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return {"id": self.params[-1], "error_json": self.params[0].obj}


def test_cancel_replaces_timeout_event_and_discards_private_operator_text() -> None:
    old_error = {**safe_job_failure("ModelTimeoutError", PRIVATE), "details": {"raw": PRIVATE}}
    cur = Cursor()
    row = _cancel_job_row(
        cur,
        current={"id": uuid4(), "status": "running", "error_json": old_error},
        reason=PRIVATE,
        requested_by=PRIVATE,
        include_running=True,
    )
    event = row["error_json"]
    assert event["public_code"] == "job_cancelled"
    assert UUID(event["error_id"]) != UUID(old_error["error_id"])
    assert event["details"] == {}
    assert "was cancelled" in public_job_error(event)
    assert PRIVATE not in json.dumps(event)
    assert "COALESCE(error_json" not in cur.query
    assert "|| error_json" not in cur.query


def test_expiry_recovery_has_fresh_safe_event_and_per_row_reference() -> None:
    cur = Cursor()
    assert recover_expired_job(cur, queue_name="extraction", job_id=uuid4()) == 1
    event = cur.params[1].obj
    assert event["public_code"] == "worker_lease_expired"
    assert event["details"] == {}
    assert "stopped responding" in public_job_error(event)
    assert "error_id" not in event
    assert "gen_random_uuid()::text" in cur.query
    assert "COALESCE(error_json" not in cur.query
    assert "|| error_json" not in cur.query
