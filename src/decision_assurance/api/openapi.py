from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from ..identity import StaticTokenAuthenticator
from ..intake.repository import SqliteIntakeRepository
from ..intake.verification import InMemoryPolicyRegistry
from ..repositories.sqlite import SqliteDecisionRepository
from ..web_research.compiler import ResearchEvidenceCompiler, SqliteDecisionEvidenceHandoff
from ..web_research.evidence_policy import EvidencePolicy
from ..web_research.normalization import EvidenceNormalizer
from ..web_research.orchestrator import ResearchOrchestrator
from ..web_research.providers.brave import BraveSearchProvider
from ..web_research.providers.firecrawl import FirecrawlContentExtractor
from ..web_research.repository import SqliteResearchRepository
from ..web_research.url_policy import PublicUrlPolicy, SystemResolver
from .app import create_app


def generate(path: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        database = Path(temporary) / "openapi.db"
        repository = SqliteDecisionRepository(database)
        intake_repository = SqliteIntakeRepository(database)
        research_repository = SqliteResearchRepository(database)
        repository.initialize()
        intake_repository.initialize()
        research_repository.initialize()
        url_policy = PublicUrlPolicy(SystemResolver())
        orchestrator = ResearchOrchestrator(
            BraveSearchProvider(api_key=None),
            FirecrawlContentExtractor(api_key=None, url_policy=url_policy),
            research_repository,
            url_policy,
            EvidenceNormalizer(max_content_bytes=1_000_000),
            EvidencePolicy(),
            ResearchEvidenceCompiler(),
            SqliteDecisionEvidenceHandoff(database),
        )
        app = create_app(
            repository,
            StaticTokenAuthenticator({}),
            intake_repository,
            InMemoryPolicyRegistry({}),
            research_repository,
            orchestrator,
        )
        path.write_text(
            json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Export deterministic OpenAPI JSON")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    generate(args.output)


if __name__ == "__main__":
    main()
