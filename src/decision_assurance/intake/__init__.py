"""Controlled Intake domain boundary for untrusted real-world input."""

from .contracts import (
    CandidateFact,
    ExtractionReport,
    FactType,
    IntakeRequest,
    IntakeStatus,
    VerificationStatus,
)
from .extractor import DeterministicQuoteExtractor, Extractor

__all__ = [
    "CandidateFact",
    "DeterministicQuoteExtractor",
    "ExtractionReport",
    "Extractor",
    "FactType",
    "IntakeRequest",
    "IntakeStatus",
    "VerificationStatus",
]
