from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import uvicorn
from fastapi import FastAPI

from ..identity import ActorKind, Identity, Role, StaticTokenAuthenticator
from ..intake.codec import policy_from_dict
from ..intake.repository import SqliteIntakeRepository
from ..intake.verification import InMemoryPolicyRegistry
from ..repositories.sqlite import SqliteDecisionRepository
from ..tenancy import TenantContext
from .app import create_app


def load_runtime(environment: dict[str, str] | None = None) -> FastAPI:
    values = environment if environment is not None else os.environ
    database_value = values.get("DA_DATABASE_PATH")
    identities_value = values.get("DA_IDENTITIES_PATH")
    if not database_value or not identities_value:
        raise RuntimeError("DA_DATABASE_PATH and DA_IDENTITIES_PATH are required")
    identities_path = Path(identities_value)
    raw = cast(dict[str, dict[str, Any]], json.loads(identities_path.read_text(encoding="utf-8")))
    identities = {
        token: Identity(
            actor_id=str(item["actor_id"]),
            tenant=TenantContext(str(item["tenant_id"])),
            role=Role(str(item["role"])),
            kind=ActorKind(str(item["kind"])),
        )
        for token, item in raw.items()
    }
    repository = SqliteDecisionRepository(Path(database_value))
    intake_repository = SqliteIntakeRepository(Path(database_value))
    repository.initialize()
    intake_repository.initialize()
    policies: dict[str, Any] = {}
    if policies_value := values.get("DA_POLICIES_PATH"):
        policies = json.loads(Path(policies_value).read_text(encoding="utf-8"))
    return create_app(
        repository,
        StaticTokenAuthenticator(identities),
        intake_repository,
        InMemoryPolicyRegistry(
            {tenant_id: policy_from_dict(item) for tenant_id, item in policies.items()}
        ),
    )


def main() -> None:
    uvicorn.run(load_runtime(), host="127.0.0.1", port=8000, log_level="info")
