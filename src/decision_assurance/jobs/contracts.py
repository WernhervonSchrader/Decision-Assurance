from __future__ import annotations

from dataclasses import dataclass

from ..production.contracts import ResearchJob


@dataclass(frozen=True, slots=True, repr=False)
class LeaseToken:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) < 12:
            raise ValueError("INVALID_LEASE_TOKEN")

    def __repr__(self) -> str:
        return "LeaseToken(**redacted**)"


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job: ResearchJob
    lease_token: LeaseToken

    def __repr__(self) -> str:
        return f"ClaimedJob(job={self.job!r}, lease_token=LeaseToken(**redacted**))"
