from pathlib import Path

ROOT = Path(__file__).parents[3]


def test_api_and_worker_images_are_non_root_and_health_checked() -> None:
    api = (ROOT / "Dockerfile.api").read_text(encoding="utf-8")
    worker = (ROOT / "Dockerfile.worker").read_text(encoding="utf-8")

    for dockerfile in (api, worker):
        assert "USER 10001:10001" in dockerfile
        assert "PYTHONDONTWRITEBYTECODE=1" in dockerfile
        assert "DA_VERSION=0.5.0" in dockerfile
        assert "COPY --from=builder" in dockerfile
    assert "HEALTHCHECK" in api
    assert "decision-assurance-api" in api
    assert "decision-assurance-worker" in worker


def test_compose_separates_api_worker_migration_and_database_roles() -> None:
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    for service in ("postgres:", "migrate:", "api:", "worker:"):
        assert service in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "DA_SECRET_DIRECTORY: /run/secrets" in compose
    assert "decision_assurance_migration" in compose
    assert "decision_assurance_application" in compose
    assert "decision_assurance_worker" in compose


def test_docker_context_excludes_secrets_vcs_and_local_databases() -> None:
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (".git", ".secrets", "*.db", ".env"):
        assert pattern in ignored
