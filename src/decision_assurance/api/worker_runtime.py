from __future__ import annotations

import asyncio
import os
import signal
import threading
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..jobs.postgresql import PostgresJobRepository
from ..jobs.worker import CancellationCheck, ResearchWorker
from ..persistence.postgresql import PostgresConnectionProvider, PostgresSettings
from ..production.config import load_config
from ..production.contracts import ResearchJob
from ..production.ports import SecretProviderPort
from ..production.secrets import FileSecretProvider
from ..tenancy import TenantContext
from ..web_research.contracts import ResearchRun, ResearchStatus
from ..web_research.orchestrator import ResearchOrchestrator
from ..web_research.ports import ResearchRepositoryPort
from .runtime import load_runtime


def load_worker(
    environment: dict[str, str] | None = None,
    *,
    external_secrets: SecretProviderPort | None = None,
    oidc_http_client: httpx.Client | None = None,
) -> tuple[ResearchWorker, PostgresJobRepository]:
    values = environment if environment is not None else dict(os.environ)
    app = load_runtime(
        values,
        external_secrets=external_secrets,
        oidc_http_client=oidc_http_client,
    )
    config_path = values.get("DA_CONFIG_PATH")
    if not config_path or external_secrets is None:
        raise RuntimeError("WORKER_PRODUCTION_CONFIGURATION_REQUIRED")
    config = load_config(Path(config_path), values)
    worker_dsn = external_secrets.resolve(config.worker_database_dsn_secret)
    worker_connections = PostgresConnectionProvider(PostgresSettings(worker_dsn))
    worker_connections.assert_safe_runtime_role("decision_assurance_worker")
    jobs = PostgresJobRepository(worker_connections, config.worker_policy)
    repository = app.state.research_repository
    orchestrator = app.state.research_orchestrator
    if not isinstance(orchestrator, ResearchOrchestrator):
        raise RuntimeError("RESEARCH_ORCHESTRATOR_REQUIRED")

    def process(job: ResearchJob, cancelled: CancellationCheck) -> bool:
        tenant = TenantContext(job.tenant_id)
        research = _required(repository, tenant, job.research_run_id)
        if cancelled():
            return False
        result = asyncio.run(
            orchestrator.execute(
                tenant,
                research.actor_id,
                research.request,
                research.expected_document_hash,
                job.correlation_id,
            )
        )
        return result.status is ResearchStatus.PARTIALLY_COMPLETED

    return ResearchWorker(jobs, process), jobs


def _required(
    repository: ResearchRepositoryPort, tenant: TenantContext, run_id: str
) -> ResearchRun:
    run = repository.get(tenant, run_id)
    if run is None:
        raise RuntimeError("RESEARCH_RUN_NOT_FOUND")
    return run


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_worker(
    worker: ResearchWorker,
    jobs: PostgresJobRepository,
    *,
    worker_id: str,
    stop: threading.Event,
) -> None:
    while not stop.is_set():
        now = _now()
        jobs.recover_stale(now=now)
        worked = worker.run_once(worker_id, now=now)
        if not worked:
            stop.wait(1.0)


def main() -> None:
    values: Mapping[str, str] = os.environ
    directory = values.get("DA_SECRET_DIRECTORY")
    if not directory:
        raise RuntimeError("DA_SECRET_DIRECTORY_REQUIRED")
    worker, jobs = load_worker(dict(values), external_secrets=FileSecretProvider(Path(directory)))
    stop = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        del signum, frame
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    run_worker(
        worker,
        jobs,
        worker_id=values.get("DA_WORKER_ID", "decision-assurance-worker"),
        stop=stop,
    )
