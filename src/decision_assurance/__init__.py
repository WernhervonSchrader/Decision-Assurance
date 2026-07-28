"""Public API for the Decision Assurance reference engine."""

from .engine import DecisionAssuranceEngine, evaluate
from .models import AssessmentResult, Finding, Outcome, Severity

__all__ = [
    "AssessmentResult",
    "DecisionAssuranceEngine",
    "Finding",
    "Outcome",
    "Severity",
    "evaluate",
]

__version__ = "0.1.0"

