import re
from pathlib import Path

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "migrations" / "postgresql"

TENANT_TABLES = (
    "decisions",
    "reports",
    "audit_events",
    "idempotency",
    "intake_records",
    "intake_facts",
    "intake_confirmations",
    "intake_audit_events",
    "intake_idempotency",
    "research_runs",
    "research_source_candidates",
    "research_source_snapshots",
    "research_evidence_candidates",
    "research_attempts",
    "research_audit_events",
    "research_idempotency",
    "research_budget_usage",
    "research_handoffs",
    "research_jobs",
    "research_job_events",
    "tenant_runtime_limits",
    "tenant_retention_policies",
    "legal_holds",
    "legal_hold_audit_events",
    "deletion_requests",
    "lifecycle_audit_events",
)


def all_migrations() -> str:
    return "\n".join(
        item.read_text(encoding="utf-8") for item in sorted(MIGRATIONS.glob("[0-9]*.sql"))
    )


def test_every_business_table_is_tenant_scoped_and_forced_rls() -> None:
    sql = all_migrations()
    assert sql
    for table in TENANT_TABLES:
        create = re.search(rf"CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\);", sql, re.DOTALL)
        assert create, table
        assert re.search(r"\btenant_id\s+TEXT\s+NOT NULL\b", create.group(1)), table
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;" in sql
        assert f"CREATE POLICY {table}_tenant_isolation ON {table}" in sql


def test_composite_relationships_and_job_idempotency_include_tenant() -> None:
    sql = all_migrations()
    assert "PRIMARY KEY (tenant_id, job_id)" in sql
    assert "UNIQUE (tenant_id, research_run_id)" in sql
    assert (
        "FOREIGN KEY (tenant_id, research_run_id) REFERENCES research_runs "
        "(tenant_id, research_run_id)"
    ) in sql
    assert "PRIMARY KEY (tenant_id, research_run_id, decision_file_id, handoff_id)" in sql


def test_database_roles_are_separate_non_owner_and_cannot_bypass_rls() -> None:
    roles = (MIGRATIONS / "roles.sql").read_text(encoding="utf-8")
    for role in (
        "decision_assurance_migration",
        "decision_assurance_application",
        "decision_assurance_operations_readonly",
        "decision_assurance_audit_export",
        "decision_assurance_worker",
    ):
        assert f"CREATE ROLE {role}" in roles
        declaration = next(line for line in roles.splitlines() if f"CREATE ROLE {role}" in line)
        assert "NOSUPERUSER" in declaration
        assert "NOBYPASSRLS" in declaration
    assert "GRANT decision_assurance_migration TO decision_assurance_application" not in roles


def test_public_and_packaged_postgresql_migrations_are_byte_identical() -> None:
    packaged = ROOT / "src" / "decision_assurance" / "migrations" / "postgresql"
    names = sorted(item.name for item in MIGRATIONS.glob("*.sql"))
    assert names == [
        "001_v0_4_baseline.sql",
        "002_production_foundation_v0_5.sql",
        "003_controlled_pilot_v0_8.sql",
        "roles.sql",
    ]
    for name in names:
        assert (MIGRATIONS / name).read_bytes() == (packaged / name).read_bytes()
