from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .contracts import ImportEnvelope


@lru_cache(maxsize=2)
def _validator(baseline: bool) -> Draft202012Validator:
    name = "strategy_baseline" if baseline else "strategy_artifact"
    path = (
        Path(__file__).parents[1]
        / "schemas"
        / "strategy"
        / "rif"
        / (name + ".v3_4_rc3.schema.json")
    )
    return Draft202012Validator(
        json.loads(path.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )


def _bounded(value: Any, depth: int = 0) -> None:
    if depth > 32:
        raise ValueError("STRATEGY_INPUT_TOO_DEEP")
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        if not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError("STRATEGY_NUMBER_INVALID")
    if isinstance(value, dict):
        if len(value) > 1000:
            raise ValueError("STRATEGY_INPUT_TOO_LARGE")
        for item in value.values():
            _bounded(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 1000:
            raise ValueError("STRATEGY_INPUT_TOO_LARGE")
        for item in value:
            _bounded(item, depth + 1)


def unique(items: list[Any]) -> set[str]:
    ids = [item["id"] if isinstance(item, dict) else item for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("STRATEGY_DUPLICATE_ID")
    return set(ids)


def refs(items: list[str], known: Any) -> None:
    if not unique(items).issubset(known):
        raise ValueError("STRATEGY_REFERENCE_INVALID")


def sources(pack: dict[str, Any]) -> set[str]:
    records = pack["sources"] + (pack.get("full_pool") or [])
    unique(pack["sources"])
    unique(pack.get("full_pool") or [])
    by_id: dict[str, Any] = {}
    for item in records:
        if item["id"] in by_id and item != by_id[item["id"]]:
            raise ValueError("STRATEGY_SOURCE_CONFLICT")
        by_id[item["id"]] = item
    for item in records:
        refs(item["cites"], by_id)
    return set(by_id)


def assumptions(
    items: list[dict[str, Any]], known: set[str], claims: set[str], options: set[str]
) -> None:
    unique(items)
    for item in items:
        if not item["claim_ids"] and not item["option_ids"]:
            raise ValueError("STRATEGY_ASSUMPTION_UNRELATED")
        refs(item["claim_ids"], claims)
        refs(item["option_ids"], options)
        refs(item["source_ids"], known)
        refs(item["counterevidence_ids"], known)


def period(value: dict[str, Any]) -> None:
    if date.fromisoformat(value["start"]) > date.fromisoformat(value["end"]):
        raise ValueError("STRATEGY_PERIOD_INVALID")


def measure(
    value: dict[str, Any], known: set[str], unit: str | None = None, span: Any = None
) -> None:
    period(value["period"])
    refs(value["source_ids"], known)
    if (unit is not None and value["unit"] != unit) or (
        span is not None and value["period"] != span
    ):
        raise ValueError("STRATEGY_MEASUREMENT_INCOMPATIBLE")


def validate_baseline(value: dict[str, Any]) -> None:
    known = sources(value["evidence"])
    claims, options = unique(value["claim_ids"]), unique(value["option_ids"])
    assumptions(value["assumptions"], known, claims, options)
    unique(value["metrics"] + value["relevant_costs"])
    for item in value["metrics"] + value["relevant_costs"]:
        measure(item["expected"], known)
    if (
        bool(value["previous_id"]) != bool(value["correction_reason"])
        or value["previous_id"] == value["id"]
    ):
        raise ValueError("STRATEGY_BASELINE_CORRECTION_INVALID")
    if datetime.fromisoformat(value["created_at"].replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("STRATEGY_TIMEZONE_REQUIRED")


def hard_status(condition: dict[str, Any], value: dict[str, Any] | None) -> str:
    if value is None or value["value"] is None:
        return "unknown"
    left, right = Fraction(str(value["value"])), Fraction(str(condition["threshold"]))
    passed = {"le": left <= right, "ge": left >= right, "eq": left == right}[condition["operator"]]
    # A numeric violation is preserved conservatively, even with unverified sources.
    return "satisfied_unverified" if passed else "violated"


def validate_import(envelope: ImportEnvelope) -> None:
    data = envelope.model_dump(mode="python")
    _bounded(data)
    try:
        if len(json.dumps(data, allow_nan=False).encode("utf-8")) > 1_048_576:
            raise ValueError("STRATEGY_INPUT_TOO_LARGE")
        validator = _validator(envelope.mode == "baseline")
        if next(validator.iter_errors(envelope.artifact), None) is not None:
            raise ValueError("STRATEGY_CONTRACT_INVALID")
    except (OverflowError, TypeError) as error:
        raise ValueError("STRATEGY_CONTRACT_INVALID") from error
    unique([report.id for report in envelope.provenance.test_reports])
    for report in envelope.provenance.test_reports:
        unique([check.id for check in report.checks])
    artifact = envelope.artifact
    if envelope.mode == "baseline":
        if envelope.selected_option_id is not None:
            raise ValueError("STRATEGY_SELECTION_UNEXPECTED")
        validate_baseline(artifact)
        return
    if datetime.fromisoformat(artifact["created_at"].replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("STRATEGY_TIMEZONE_REQUIRED")
    request, results = artifact["request"], artifact["results"]
    known = sources(request["evidence"])
    claims = unique(request["claims"])
    unique(request["input_refs"])
    for claim in request["claims"]:
        refs(claim["source_ids"], known)
    options = request["options"]
    option_ids = unique(options["options"]) if options else set()
    assumptions(request["assumptions"] or [], known, claims, option_ids)
    if unique(results["assumptions"]) != unique(request["assumptions"] or []):
        raise ValueError("STRATEGY_RESULT_REFERENCES_INVALID")
    state = artifact["evidence_state"]
    if (
        state["evidence_pack"] != request["evidence"]
        or state["claims"] != request["claims"]
        or state["current_date"] != request["as_of"]
    ):
        raise ValueError("STRATEGY_EVIDENCE_CONTEXT_MISMATCH")
    refs(state["validated_source_ids"], known)
    for item in state["findings"]:
        refs(item.get("source_ids", []), known)
        refs(item.get("claim_ids", []), claims)
    skill_fields = {
        "assumption-audit": "assumptions",
        "strategic-options": "options",
        "value-realization": "value",
    }
    unique_names = [s["name"] for s in artifact["skills"]]
    if len(set(unique_names)) != len(unique_names) or set(unique_names) != {
        s for s, field in skill_fields.items() if request[field] is not None
    }:
        raise ValueError("STRATEGY_SKILL_METADATA_INVALID")
    expected_audit = [(s, "analyze", "ANALYSIS_ONLY", request["id"]) for s in unique_names]
    actual_audit = [
        (e["node"], e["action"], e["status"], e["detail"]) for e in artifact["analysis_audit"]
    ]
    if actual_audit != expected_audit:
        raise ValueError("STRATEGY_ANALYSIS_AUDIT_INVALID")
    for event in artifact["analysis_audit"] + state["audit_trail"]:
        if datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("STRATEGY_TIMEZONE_REQUIRED")
    if options:
        _validate_options(options, results, known)
    elif results["options"] or results["scenarios"] or results["rank_changes"]:
        raise ValueError("STRATEGY_UNEXPECTED_RESULTS")
    if envelope.selected_option_id is not None and envelope.selected_option_id not in option_ids:
        raise ValueError("STRATEGY_OPTION_REFERENCE_INVALID")
    if envelope.mode == "draft" and options and envelope.selected_option_id is None:
        raise ValueError("STRATEGY_SELECTED_OPTION_REQUIRED")
    if envelope.mode == "observation" and (
        request["value"] is None or envelope.selected_option_id is not None
    ):
        raise ValueError("STRATEGY_OBSERVATION_INVALID")
    baseline, value = artifact["baseline"], request["value"]
    if value:
        if not baseline or baseline["id"] != value["baseline_id"]:
            raise ValueError("STRATEGY_BASELINE_REFERENCE_INVALID")
        validate_baseline(baseline)
        if datetime.fromisoformat(
            artifact["created_at"].replace("Z", "+00:00")
        ) < datetime.fromisoformat(baseline["created_at"].replace("Z", "+00:00")):
            raise ValueError("STRATEGY_BASELINE_TIME_INVALID")
        metrics = {m["id"]: m for m in baseline["metrics"] + baseline["relevant_costs"]}
        refs(list(value["actuals"]), metrics)
        for key, actual in value["actuals"].items():
            expected = metrics[key]["expected"]
            measure(actual, known, expected["unit"], expected["period"])
            if actual["value"] is not None and date.fromisoformat(
                actual["period"]["end"]
            ) > date.fromisoformat(request["as_of"]):
                raise ValueError("STRATEGY_FUTURE_OBSERVATION")
        for ids in [value["execution_source_ids"], value["causal_source_ids"]] + [
            e["source_ids"] for e in value["competing_explanations"]
        ]:
            refs(ids, known)
        if unique(results["comparisons"]) != set(metrics):
            raise ValueError("STRATEGY_COMPARISON_REFERENCES_INVALID")
    elif (
        baseline is not None
        or results["comparisons"]
        or results["execution"] != "not_assessed"
        or results["attribution"] != "not_assessed"
    ):
        raise ValueError("STRATEGY_UNEXPECTED_BASELINE")


def _validate_options(options: dict[str, Any], results: dict[str, Any], known: set[str]) -> None:
    option_ids, criteria, conditions = (
        unique(options["options"]),
        unique(options["criteria"]),
        unique(options["hard_conditions"]),
    )
    scenarios = unique(options["scenarios"])
    period(options["period"])
    kinds = {o["kind"] for o in options["options"]}
    for kind, reason in [
        ("status_quo", "status_quo_exclusion_reason"),
        ("pilot", "pilot_exclusion_reason"),
    ]:
        if kind not in kinds and options[reason] is None:
            raise ValueError("STRATEGY_ALTERNATIVE_REASON_REQUIRED")
    for criterion in options["criteria"]:
        if criterion["minimum"] >= criterion["maximum"]:
            raise ValueError("STRATEGY_SCALE_INVALID")
    for option in options["options"]:
        refs(list(option["hard_values"]), conditions)
        for condition in options["hard_conditions"]:
            value = option["hard_values"].get(condition["id"])
            if value:
                measure(value, known, condition["unit"], options["period"])
    for scenario in options["scenarios"]:
        if (
            set(scenario["weights"]) != criteria
            or any(w < 0 for w in scenario["weights"].values())
            or sum((Fraction(str(w)) for w in scenario["weights"].values()), Fraction()) != 1
        ):
            raise ValueError("STRATEGY_WEIGHTS_INVALID")
        refs(list(scenario["values"]), option_ids)
        for values in scenario["values"].values():
            refs(list(values), criteria)
            for criterion in options["criteria"]:
                value = values.get(criterion["id"])
                if value:
                    measure(value, known, criterion["unit"], options["period"])
                    if (
                        value["value"] is not None
                        and not criterion["minimum"] <= value["value"] <= criterion["maximum"]
                    ):
                        raise ValueError("STRATEGY_SCALE_INVALID")
    if unique(results["options"]) != option_ids or unique(results["scenarios"]) != scenarios:
        raise ValueError("STRATEGY_RESULT_REFERENCES_INVALID")
    eligible: set[str] = set()
    for option in results["options"]:
        if set(option["conditions"]) != conditions:
            raise ValueError("STRATEGY_CONDITION_REFERENCES_INVALID")
        expected = (
            "ineligible"
            if "violated" in option["conditions"].values()
            else "unknown"
            if "unknown" in option["conditions"].values()
            else "eligible"
        )
        if option["eligibility"] != expected:
            raise ValueError("STRATEGY_ELIGIBILITY_INCONSISTENT")
        source = next(o for o in options["options"] if o["id"] == option["id"])
        for condition in options["hard_conditions"]:
            if (
                hard_status(condition, source["hard_values"].get(condition["id"])) == "violated"
                and option["conditions"][condition["id"]] == "satisfied"
            ):
                raise ValueError("STRATEGY_HARD_CONDITION_CONTRADICTION")
        if option["eligibility"] == "eligible":
            eligible.add(option["id"])
    for scenario in results["scenarios"]:
        refs(list(scenario["scores"]), eligible)
        ranking = [ref for group in scenario["ranking"] for ref in group]
        refs(ranking, eligible)
        if any(not group for group in scenario["ranking"]):
            raise ValueError("STRATEGY_RANKING_INVALID")
        if scenario["winner"] is not None:
            if (
                scenario["status"] != "ranked"
                or not scenario["ranking"]
                or scenario["ranking"][0] != [scenario["winner"]]
            ):
                raise ValueError("STRATEGY_WINNER_INVALID")
        elif scenario["status"] == "ranked":
            raise ValueError("STRATEGY_WINNER_INVALID")
        if set(ranking) != set(scenario["scores"]):
            raise ValueError("STRATEGY_RANKING_INVALID")
        try:
            if any(
                re.fullmatch(r"-?[0-9]{1,50}(?:/[0-9]{1,50})?", value) is None
                for value in scenario["scores"].values()
            ):
                raise ValueError("STRATEGY_SCORE_INVALID")
            scores = {
                key: Fraction(value)
                for key, value in scenario["scores"].items()
                if len(value) <= 100
            }
            if len(scores) != len(scenario["scores"]) or any(
                score < 0 or score > 1 for score in scores.values()
            ):
                raise ValueError("STRATEGY_SCORE_INVALID")
            groups = [scores[group[0]] for group in scenario["ranking"]]
            if groups != sorted(set(groups), reverse=True) or any(
                len({scores[k] for k in group}) != 1 for group in scenario["ranking"]
            ):
                raise ValueError("STRATEGY_RANKING_INVALID")
        except (ZeroDivisionError, ValueError) as error:
            raise ValueError("STRATEGY_SCORE_INVALID") from error
