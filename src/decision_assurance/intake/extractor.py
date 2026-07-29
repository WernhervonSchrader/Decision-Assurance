from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Protocol

from .contracts import (
    CandidateFact,
    ExtractionReport,
    FactType,
    IntakeConflict,
    SourceReference,
    VerificationRequirement,
)


class Extractor(Protocol):
    def extract(
        self, raw_input: str, *, locale: str, intake_id: str = "ad-hoc"
    ) -> ExtractionReport: ...


class DeterministicQuoteExtractor:
    method = "deterministic-quote"
    version = "0.3.0"

    _money = re.compile(
        r"(?<![\w.-])(?P<number>\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)\s*(?P<currency>EUR|USD|€|\$)",
        re.IGNORECASE,
    )
    _percent = re.compile(r"(?<![\d.,])(?P<number>\d+(?:[.,]\d+)?)\s*%")
    _payment = re.compile(
        r"(?:zahlungsziel|payment\s+terms?)\D{0,12}(?P<number>\d+)\s*(?:tage|days?)", re.IGNORECASE
    )
    _duration = re.compile(
        r"(?:laufzeit|duration|term)\D{0,12}(?P<number>\d+)\s*(?:monate?|months?)", re.IGNORECASE
    )
    _date = re.compile(r"\b(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{4})\b")
    _policy = re.compile(
        r"\b(?:EX-\d{4}-\d{2}|[A-Z][A-Za-z ]+Policy\s+\d{4}(?:,?\s*Version\s*[\d.]+)?)\b"
    )
    _approval = re.compile(
        r"[^.!?]*(?:freigab\w*|freigegeb\w*|genehmig\w*|approv\w*)[^.!?]*[.!?]?",
        re.IGNORECASE,
    )
    _roles = re.compile(
        r"\b(?:generator|validator|approver|ersteller|prüfer|finance|sales|management)\b",
        re.IGNORECASE,
    )
    _instruction = re.compile(
        r"[^.!?]*(?:ignore|ignoriere|setze?|return)\s+[^.!?]*(?:PASS|APPROVED|regeln|rules)[^.!?]*[.!?]?",
        re.IGNORECASE,
    )

    def extract(
        self, raw_input: str, *, locale: str, intake_id: str = "ad-hoc"
    ) -> ExtractionReport:
        if locale not in {"de", "en"}:
            locale = "en"
        source_hash = f"sha256:{hashlib.sha256(raw_input.encode('utf-8')).hexdigest()}"
        found: list[tuple[int, int, FactType, str, str | None, str | None, str | None, float]] = []

        occupied: set[tuple[int, int]] = set()
        for pattern, fact_type, unit in (
            (self._payment, FactType.PAYMENT_TERM_DAYS, "days"),
            (self._duration, FactType.DURATION_MONTHS, "months"),
        ):
            for match in pattern.finditer(raw_input):
                found.append(
                    (
                        match.start(),
                        match.end(),
                        fact_type,
                        match.group(0),
                        match.group("number"),
                        unit,
                        None,
                        0.98,
                    )
                )
                occupied.add((match.start(), match.end()))

        for match in self._money.finditer(raw_input):
            number = self._normalize_number(match.group("number"), locale)
            currency = "EUR" if match.group("currency").upper() in {"EUR", "€"} else "USD"
            found.append(
                (
                    match.start(),
                    match.end(),
                    FactType.AMOUNT,
                    match.group(0),
                    number,
                    None,
                    currency,
                    0.99,
                )
            )

        for match in self._percent.finditer(raw_input):
            if any(start <= match.start() and match.end() <= end for start, end in occupied):
                continue
            fact_type = self._percent_type(raw_input, match.start(), match.end())
            found.append(
                (
                    match.start(),
                    match.end(),
                    fact_type,
                    match.group(0),
                    self._normalize_number(match.group("number"), locale),
                    "percent",
                    None,
                    0.97,
                )
            )

        for match in self._date.finditer(raw_input):
            date_context = raw_input[max(0, match.start() - 30) : match.start()].lower()
            date_type = (
                FactType.EVIDENCE_DATE
                if any(term in date_context for term in ("bonitätsprüfung", "credit check"))
                else FactType.DATE
            )
            found.append(
                (
                    match.start(),
                    match.end(),
                    date_type,
                    match.group(0),
                    self._normalize_date(match.group("date")),
                    None,
                    None,
                    0.96,
                )
            )
        for pattern, fact_type, confidence in (
            (self._policy, FactType.POLICY_CLAIM, 0.88),
            (self._approval, FactType.APPROVAL_CLAIM, 0.82),
            (self._roles, FactType.ROLE_CLAIM, 0.9),
            (self._instruction, FactType.UNTRUSTED_INSTRUCTION, 0.99),
        ):
            for match in pattern.finditer(raw_input):
                raw = match.group(0).strip()
                start = raw_input.find(raw, match.start(), match.end() + 1)
                found.append((start, start + len(raw), fact_type, raw, raw, None, None, confidence))

        found.sort(key=lambda item: (item[0], item[2].value, item[3]))
        candidates = [
            CandidateFact(
                fact_id=f"{intake_id}:fact:{index}",
                fact_type=item[2],
                raw_value=item[3],
                normalized_value=item[4],
                unit=item[5],
                currency=item[6],
                source=SourceReference("raw-input", item[0], item[1], source_hash),
                method=self.method,
                method_version=self.version,
                extraction_confidence=item[7],
            )
            for index, item in enumerate(found, 1)
        ]
        conflicts = self._conflicts(intake_id, candidates)
        conflict_by_fact = {
            fact_ref: conflict.conflict_id
            for conflict in conflicts
            for fact_ref in conflict.fact_refs
        }
        candidates = [
            replace(candidate, conflict_refs=(conflict_by_fact[candidate.fact_id],))
            if candidate.fact_id in conflict_by_fact
            else candidate
            for candidate in candidates
        ]
        requirements = self._missing_requirements(intake_id, raw_input)
        return ExtractionReport(
            "0.3.0",
            intake_id,
            self.method,
            self.version,
            locale,
            tuple(candidates),
            tuple(conflicts),
            tuple(requirements),
        )

    @staticmethod
    def _normalize_number(value: str, locale: str) -> str:
        normalized = value
        if locale == "de":
            normalized = normalized.replace(".", "").replace(",", ".")
        elif "," in normalized and "." not in normalized:
            parts = normalized.split(",")
            normalized = "".join(parts) if len(parts[-1]) == 3 else ".".join(parts)
        else:
            normalized = normalized.replace(",", "")
        try:
            number = Decimal(normalized)
        except InvalidOperation:
            return value
        return format(number, "f")

    @staticmethod
    def _normalize_date(value: str) -> str:
        day, month, year = re.split(r"[./-]", value)
        return f"{year}-{int(month):02d}-{int(day):02d}"

    @staticmethod
    def _percent_type(text: str, start: int, end: int) -> FactType:
        window_start = max(0, start - 40)
        context = text[window_start : min(len(text), end + 24)].lower()
        if re.search(r"mindestmarge|minimum\s+margin|min\.??\s*margin", context):
            return FactType.MIN_MARGIN_PERCENT
        if re.search(r"(?:rabatt|discount).*(?:grenze|limit|höchst|max)", context):
            return FactType.DISCOUNT_LIMIT_PERCENT
        number_position = start - window_start

        def nearest(*terms: str) -> int:
            distances = []
            for term in terms:
                for match in re.finditer(term, context):
                    if match.end() <= number_position:
                        distances.append(number_position - match.end())
                    else:
                        distances.append(match.start() - number_position)
            return min(distances, default=10_000)

        margin_distance = nearest("marge", "margin", "deckungsbeitrag")
        discount_distance = nearest("rabatt", "discount")
        return (
            FactType.MARGIN_PERCENT
            if margin_distance < discount_distance
            else FactType.DISCOUNT_PERCENT
        )

    @staticmethod
    def _conflicts(intake_id: str, candidates: list[CandidateFact]) -> list[IntakeConflict]:
        conflicts: list[IntakeConflict] = []
        for fact_type in (FactType.AMOUNT, FactType.DISCOUNT_PERCENT, FactType.MARGIN_PERCENT):
            group = [item for item in candidates if item.fact_type is fact_type]
            if len({item.normalized_value for item in group}) > 1:
                conflicts.append(
                    IntakeConflict(
                        f"{intake_id}:conflict:{len(conflicts) + 1}",
                        fact_type,
                        tuple(item.fact_id for item in group),
                    )
                )
        return conflicts

    @staticmethod
    def _missing_requirements(intake_id: str, text: str) -> list[VerificationRequirement]:
        lowered = text.lower()
        requirements: list[VerificationRequirement] = []
        missing_patterns = (
            (FactType.MARGIN_PERCENT, ("margenkalkulation fehlt", "margin calculation missing")),
            (
                FactType.APPROVAL_CLAIM,
                ("freigabe liegt nicht vor", "approval missing", "freigabe fehlt"),
            ),
        )
        for fact_type, phrases in missing_patterns:
            if any(phrase in lowered for phrase in phrases):
                requirements.append(
                    VerificationRequirement(
                        f"{intake_id}:requirement:{len(requirements) + 1}",
                        fact_type,
                        "MANDATORY_INFORMATION_MISSING",
                    )
                )
        return requirements
