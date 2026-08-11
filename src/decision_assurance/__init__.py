"""Public API for the Decision Assurance reference engine."""

from .decision_file import (
    DecisionFileSemanticError,
    approval_digest,
    bind_approval,
    bind_canonical_action,
    canonical_action_digest,
    evaluate_decision_file,
    load_decision_file,
    migrate_decision_file_v0_1_to_v0_2,
    validate_semantics,
)
from .engine import DecisionAssuranceEngine, evaluate
from .models import AssessmentResult, Finding, Outcome, Severity
from .transitions import CaseStatus, TransitionPolicy, TransitionRejected

__all__ = [
    "AssessmentResult",
    "DecisionAssuranceEngine",
    "DecisionFileSemanticError",
    "CaseStatus",
    "Finding",
    "Outcome",
    "Severity",
    "TransitionPolicy",
    "TransitionRejected",
    "approval_digest",
    "bind_approval",
    "bind_canonical_action",
    "canonical_action_digest",
    "evaluate",
    "evaluate_decision_file",
    "load_decision_file",
    "migrate_decision_file_v0_1_to_v0_2",
    "validate_semantics",
]

__version__ = "0.5.0"
