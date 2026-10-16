from __future__ import annotations

import copy
from collections.abc import Callable
from threading import RLock
from typing import Any

from .contracts import digest


class ExecutionSandbox:
    """Test-only atomic state/approval boundary. No production I/O or tool dispatch."""

    def __init__(self, tenant_id: str, *, amount: int = 10000, now: int = 100):
        if tenant_id not in {"tenant-a", "tenant-b"}:
            raise ValueError("TENANT_CONTEXT_REQUIRED")
        self.tenant_id = tenant_id
        self.now = now
        self.state: dict[str, Any] = {
            "tenant_id": tenant_id,
            "object_id": "purchase-1",
            "price": amount,
            "supplier": "supplier-verified",
            "bank": "synthetic-bank-original",
            "version": 1,
            "contract_valid_until": 200,
        }
        self.original = copy.deepcopy(self.state)
        self._approvals: dict[str, dict[str, Any]] = {}
        self._denied: set[tuple[str, str]] = set()
        self._used: set[str] = set()
        self._lock = RLock()
        self.audit_available = True
        self.events: list[dict[str, Any]] = []
        self.effects: list[dict[str, Any]] = []

    def approve(self) -> dict[str, Any]:
        """Trusted test harness, independent of the simulated generator's proposal."""
        with self._lock:
            grant = {
                "grant_id": f"grant-{len(self._approvals) + 1}",
                "tenant_id": self.tenant_id,
                "object_id": self.state["object_id"],
                "action": "purchase.execute",
                "state_digest": digest(self.state),
                "valid_until": 200,
                "approver_id": "independent-human",
                "approver_kind": "HUMAN",
            }
            self._approvals[grant["grant_id"]] = copy.deepcopy(grant)
            return copy.deepcopy(grant)

    def change(self, change: str) -> None:
        with self._lock:
            changes = {
                "price": ("price", 13000),
                "supplier": ("supplier", "supplier-other"),
                "bank": ("bank", "synthetic-bank-email-claim"),
                "expired": ("contract_valid_until", 99),
                "version": ("version", 2),
                "tenant": ("tenant_id", "tenant-other"),
                "forged": ("generator_validated", True),
            }
            if change == "restore":
                self.state = copy.deepcopy(self.original)
            elif change in changes:
                key, value = changes[change]
                self.state[key] = value
            else:
                raise ValueError("UNKNOWN_STATE_MUTATION")

    def execute(
        self,
        grant: dict[str, Any],
        *,
        wording: str = "execute",
        before_commit: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        del wording  # Rephrasing cannot alter the canonical object/action identity.
        with self._lock:
            if before_commit:
                before_commit()
            key = (self.tenant_id, "purchase-1:purchase.execute")
            trusted = self._approvals.get(str(grant.get("grant_id")))
            freshness = (
                self.state["contract_valid_until"] > self.now
                and trusted is not None
                and trusted["state_digest"] == digest(self.state)
                and trusted["valid_until"] > self.now
            )
            authorized = (
                trusted == grant
                and trusted is not None
                and grant["tenant_id"] == self.tenant_id == self.state["tenant_id"]
                and grant["approver_kind"] == "HUMAN"
                and grant["approver_id"] != "generator"
                and key not in self._denied
                and grant["grant_id"] not in self._used
            )
            allowed = bool(authorized and freshness)
            if not self.audit_available:
                return {
                    "executed": False,
                    "audit_complete": False,
                    "freshness_valid": bool(freshness),
                    "error_code": "AUDIT_UNAVAILABLE",
                    "event_types": [],
                }
            code = "EXECUTED" if allowed else "EXECUTION_BLOCKED"
            event = {
                "sequence": len(self.events) + 1,
                "tenant_id": self.tenant_id,
                "actor": "sandbox-executor",
                "target": "purchase-1",
                "action": "purchase.execute",
                "timestamp": self.now,
                "correlation_id": "sandbox-request",
                "source_channel": "benchmark",
                "reason_code": code,
                "previous_hash": digest(self.events[-1]) if self.events else None,
                "state_digest": digest(self.state),
            }
            self.events.append(event)
            if allowed:
                self._used.add(grant["grant_id"])
                self.effects.append({"tenant_id": self.tenant_id, "object_id": "purchase-1"})
            else:
                self._denied.add(key)
            return {
                "executed": allowed,
                "audit_complete": True,
                "freshness_valid": bool(freshness),
                "error_code": None,
                "event_types": [x["reason_code"] for x in self.events],
            }
