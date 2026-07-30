from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..intake.postgresql_repository import PostgresIntakeRepository
from ..intake.repository import IntakeRepository, SqliteIntakeRepository
from ..production.contracts import DatabaseBackend, EnvironmentProfile, SecretValue
from ..repositories.postgresql import PostgresDecisionRepository
from ..repositories.protocols import DecisionRepository
from ..repositories.sqlite import SqliteDecisionRepository
from ..web_research.postgresql_repository import PostgresResearchRepository
from ..web_research.repository import SqliteResearchRepository
from .postgresql import PostgresConnectionProvider, PostgresSettings

ResearchRepository = SqliteResearchRepository | PostgresResearchRepository


@dataclass(frozen=True, slots=True)
class PersistenceBundle:
    backend: DatabaseBackend
    decisions: DecisionRepository
    intake: IntakeRepository
    research: ResearchRepository
    connections: PostgresConnectionProvider | None = None


def create_persistence(
    *,
    profile: EnvironmentProfile,
    backend: DatabaseBackend,
    sqlite_path: Path | None = None,
    postgres_dsn: SecretValue | None = None,
) -> PersistenceBundle:
    if profile is EnvironmentProfile.PRODUCTION and backend is not DatabaseBackend.POSTGRESQL:
        raise ValueError("PRODUCTION_REQUIRES_POSTGRESQL")
    if backend is DatabaseBackend.SQLITE:
        if sqlite_path is None:
            raise ValueError("SQLITE_PATH_REQUIRED")
        decisions = SqliteDecisionRepository(sqlite_path)
        intake = SqliteIntakeRepository(sqlite_path)
        research = SqliteResearchRepository(sqlite_path)
        decisions.initialize()
        intake.initialize()
        research.initialize()
        return PersistenceBundle(backend, decisions, intake, research)
    if postgres_dsn is None:
        raise ValueError("POSTGRES_DSN_REQUIRED")
    connections = PostgresConnectionProvider(PostgresSettings(postgres_dsn))
    return PersistenceBundle(
        backend,
        PostgresDecisionRepository(connections),
        PostgresIntakeRepository(connections),
        PostgresResearchRepository(connections),
        connections,
    )
