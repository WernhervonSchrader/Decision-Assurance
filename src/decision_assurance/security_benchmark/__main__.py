from __future__ import annotations

import json
from itertools import chain
from pathlib import Path
from typing import Any

import click

from .annotations import annotate_index
from .cases import fp_cases, full_cases, own_cases, selected_cases, smoke_cases
from .contracts import ROOT, read_json, validate_case
from .dataset import LOCK_PATH, acquire_dataset, build_index, verify_file
from .reporting import attach_metadata, message, write_report
from .runner import compare_reports, compare_stream_reports, run_cases


@click.group(help=message("cli_help"))
def main() -> None:
    """DA security benchmark. Source acquisition is separate from offline execution."""


@main.command("import-dataset")
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--include-annotations", is_flag=True, help=message("annotation_help"))
def import_dataset(output: Path, include_annotations: bool) -> None:
    try:
        manifest = acquire_dataset(output, include_annotations=include_annotations)
        click.echo(
            json.dumps({"revision": manifest["revision"], "verified_files": len(manifest["files"])})
        )
    except Exception as error:
        raise click.ClickException(f"DATASET_IMPORT_FAILED:{type(error).__name__}") from None


@main.command("verify-fixtures")
@click.option("--raw-root", type=click.Path(path_type=Path), required=True)
def verify_fixtures(raw_root: Path) -> None:
    from .fixtures import verify_smoke_origins

    try:
        click.echo(json.dumps(verify_smoke_origins(raw_root)))
    except (ValueError, OSError, KeyError):
        raise click.ClickException("FIXTURE_ORIGIN_VERIFICATION_FAILED") from None


@main.command()
@click.option("--raw-root", type=click.Path(path_type=Path), required=True)
@click.option("--index", type=click.Path(path_type=Path), required=True)
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--profile", type=click.Choice(["smoke", "standard"]), default="standard")
@click.option("--seed", type=int, default=42)
def prepare(raw_root: Path, index: Path, output: Path, profile: str, seed: int) -> None:
    try:
        for file in read_json(LOCK_PATH)["files"]:
            if file["kind"] in {"raw", "annotations"}:
                verify_file(raw_root / file["path"], file["sha256"], file["size"])
        summary = build_index(sorted((raw_root / "data").glob("raw_submissions*.jsonl")), index)
        summary.update(
            annotate_index(index, sorted((raw_root / "data").glob("labelled_unique*.json")))
        )
        attacks = selected_cases(index, raw_root, profile, seed)
        benign = fp_cases(raw_root)
        cases = attacks + (benign[:4] if profile == "smoke" else benign) + own_cases(profile)
        for case in cases:
            validate_case(case)
        output.parent.mkdir(parents=True, exist_ok=True)
        catalog = {
            "schema_version": "0.1",
            "profile": profile,
            "seed": seed,
            "selection": "seeded-sha256-ranked round-robin across original scenario and first derived category; payload-hash dedup",
            "source_summary": summary,
            "cases": cases,
        }
        output.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf8")
        click.echo(
            json.dumps({"cases": len(cases), "attacks": len(attacks), "source_summary": summary})
        )
    except Exception as error:
        raise click.ClickException(f"PREPARE_FAILED:{type(error).__name__}") from None


@main.command()
@click.option("--profile", type=click.Choice(["smoke", "standard", "full"]), default="smoke")
@click.option("--cases", "case_path", type=click.Path(path_type=Path))
@click.option("--payload-root", type=click.Path(path_type=Path))
@click.option("--output", type=click.Path(path_type=Path), required=True)
@click.option("--checkpoint", type=click.Path(path_type=Path))
@click.option("--baseline", type=click.Path(path_type=Path))
@click.option("--locale", type=str)
@click.option("--seed", type=int, default=42)
def run(
    profile: str,
    case_path: Path | None,
    payload_root: Path | None,
    output: Path,
    checkpoint: Path | None,
    baseline: Path | None,
    locale: str | None,
    seed: int,
) -> None:
    try:
        report: dict[str, Any]
        if profile == "full":
            if payload_root is None or case_path is not None:
                raise ValueError("FULL_REQUIRES_RAW_ROOT")
            from .streaming import run_streaming

            report = run_streaming(
                chain(full_cases(payload_root), fp_cases(payload_root), own_cases("standard")),
                output,
                payload_root=payload_root,
                profile=profile,
                seed=seed,
            )
        else:
            if case_path:
                catalog = read_json(case_path)
                if catalog["profile"] != profile or catalog["seed"] != seed:
                    raise ValueError("PROFILE_OR_SEED_MISMATCH")
                cases = catalog["cases"]
            elif profile == "smoke":
                cases = smoke_cases()
                payload_root = ROOT / "benchmarks/security/fixtures"
            else:
                raise ValueError("STANDARD_REQUIRES_PREPARED_CASES")
            report = run_cases(
                cases,
                output / "work",
                payload_root=payload_root,
                checkpoint=checkpoint,
                profile=profile,
                seed=seed,
            )
        attach_metadata(report)
        regression = None
        if baseline:
            previous = read_json(baseline)
            regression = (
                compare_stream_reports(previous, report, baseline.parent, output)
                if profile == "full"
                else compare_reports(previous, report)
            )
            report["regression_findings"] = regression["regressions"]
        write_report(report, output, locale)
        click.echo(
            json.dumps(
                {
                    "total": report["total_cases"],
                    "counts": report["counts"],
                    "regression_pass": regression["regression_pass"] if regression else None,
                    "security_pass": report["counts"]["SECURITY_FAILURE"] == 0,
                }
            )
        )
        if report["counts"]["TEST_ERROR"] or report["counts"]["INFRASTRUCTURE_ERROR"]:
            raise click.exceptions.Exit(3)
        if (regression and not regression["regression_pass"]) or (
            not baseline and report["counts"]["SECURITY_FAILURE"]
        ):
            raise click.exceptions.Exit(2)
    except click.exceptions.Exit:
        raise
    except Exception as error:
        raise click.ClickException(f"BENCHMARK_RUN_FAILED:{type(error).__name__}") from None


@main.command()
@click.option("--baseline", type=click.Path(path_type=Path), required=True)
@click.option("--report", type=click.Path(path_type=Path), required=True)
def compare(baseline: Path, report: Path) -> None:
    try:
        previous, current = read_json(baseline), read_json(report)
        comparison = (
            compare_stream_reports(previous, current, baseline.parent, report.parent)
            if previous.get("result_stream") or current.get("result_stream")
            else compare_reports(previous, current)
        )
        click.echo(json.dumps(comparison, indent=2))
        if not comparison["regression_pass"]:
            raise click.exceptions.Exit(2)
    except (ValueError, KeyError, OSError):
        raise click.ClickException("REGRESSION_INPUT_INVALID") from None


if __name__ == "__main__":
    main()
