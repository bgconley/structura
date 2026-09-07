"""Rollback-only historical schema reconstruction, never an application migration."""

from pathlib import Path
from typing import LiteralString, cast

from psycopg.sql import SQL


def restore_105(cur):
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='structura' "
        "AND table_name='native_claim_sets' AND column_name='interpretation_kind') AS present"
    )
    if not cur.fetchone()["present"]:
        return
    cur.execute(
        "DROP FUNCTION guard_native_claim_set(),guard_native_claim_content(),"
        "retain_native_claim_history() CASCADE"
    )
    cur.execute("DELETE FROM extraction_claims WHERE origin_kind='native_model_emission'")
    cur.execute(
        "DELETE FROM native_claim_page_checkpoints WHERE claim_set_id IN "
        "(SELECT id FROM native_claim_sets WHERE interpretation_kind='model_emission')"
    )
    cur.execute("DELETE FROM native_claim_sets WHERE interpretation_kind='model_emission'")
    cur.execute("""ALTER TABLE extraction_claims DROP CONSTRAINT extraction_claim_origin_branch,
        DROP CONSTRAINT extraction_claim_value_types,DROP COLUMN native_member_index,
        DROP COLUMN native_member_sha256,
        ADD CONSTRAINT extraction_claims_value_type_check CHECK(value_type IN
          ('money','date','quantity','identifier','party','enum','text','number','boolean','object'))""")
    cur.execute("""ALTER TABLE native_claim_page_checkpoints DROP COLUMN source_checkpoint_sha256,
        DROP COLUMN source_members_json,
        DROP CONSTRAINT native_claim_page_count_bound,
        ADD CONSTRAINT native_claim_page_checkpoints_claim_count_check
          CHECK(claim_count BETWEEN 0 AND 1000)""")
    cur.execute(
        "ALTER TABLE document_parse_page_checkpoints "
        "DROP CONSTRAINT parse_checkpoint_content_identity"
    )
    cur.execute("ALTER TABLE native_claim_sets DROP COLUMN interpretation_kind")
    migration = (
        Path(__file__).resolve().parents[3] / "database/105_completion_native_claim_currency.sql"
    ).read_text()
    branch = migration.split("ADD CONSTRAINT extraction_claim_origin_branch CHECK (", 1)[1].split(
        "\n  );\nCREATE INDEX", 1
    )[0]
    cur.execute(
        SQL(
            cast(
                LiteralString,
                "ALTER TABLE extraction_claims ADD CONSTRAINT "
                "extraction_claim_origin_branch CHECK (" + branch + "\n)",
            )
        ),
        prepare=False,
    )
    functions = migration[migration.index("CREATE FUNCTION guard_native_claim_set()") :]
    cur.execute(SQL(cast(LiteralString, functions)), prepare=False)
