"""Public API for the Decision Assurance reference engine."""

from .engine import DecisionAssuranceEngine, evaluate
from .decision_file import DecisionFileSemanticError, evaluate_decision_file, load_decision_file, validate_semantics
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
    "evaluate",
    "evaluate_decision_file",
    "load_decision_file",
    "validate_semantics",
]

__version__ = "0.1.0"
