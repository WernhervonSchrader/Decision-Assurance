from __future__ import annotations

import json
import os
import shutil

# Only fixed, read-only Git metadata commands are run below.
import subprocess  # nosec B404
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..i18n import select_locale
from .contracts import ROOT, digest, read_json
from .dataset import LOCK_PATH


def locale_name(requested: str | None) -> str:
    return select_locale(requested or os.environ.get("LC_ALL") or os.environ.get("LANG"))


def message(key: str, locale: str | None = None) -> str:
    return str(read_json(Path(__file__).with_name("locales.json"))[locale_name(locale)][key])


def format_number(value: int | float, locale: str, *, percentage: bool = False) -> str:
    rendered = f"{value * 100:,.2f}%" if percentage else f"{value:,}"
    if locale == "de":
        rendered = rendered.translate(str.maketrans(",.", ".,"))
        if percentage:
            rendered = rendered[:-1] + " %"
    return rendered


def _git_value(args: list[str]) -> str:
    if args not in (["rev-parse", "HEAD"], ["status", "--porcelain"]):
        raise ValueError("GIT_METADATA_OPERATION_REJECTED")
    try:
        executable = shutil.which("git")
        if executable is None:
            return "UNKNOWN"
        return subprocess.run(  # noqa: S603  # nosec B603
            [executable, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN"


def attach_metadata(report: dict[str, Any]) -> dict[str, Any]:
    lock = read_json(LOCK_PATH)
    report.update(
        repository_commit=_git_value(["rev-parse", "HEAD"]),
        repository_dirty=bool(_git_value(["status", "--porcelain"])),
        dataset_revision=lock["revision"],
        dataset_checksum=digest(lock),
        generated_at=datetime.now(timezone.utc).isoformat(),
        evidence_class="REPOSITORY_TEST_EVIDENCE_NOT_PRODUCTION_AUTHORIZATION",
    )
    return report


def markdown_report(report: dict[str, Any], locale: str | None = None) -> str:
    selected = locale_name(locale)
    catalogs = read_json(Path(__file__).with_name("locales.json"))
    text = catalogs[selected]
    lines = [f"# {text['title']}", "", text["scope"], ""]
    for key in (
        "benchmark_version",
        "repository_commit",
        "dataset_revision",
        "dataset_checksum",
        "execution_mode",
        "profile",
    ):
        lines.append(f"**{text[key]}:** `{report.get(key, 'UNKNOWN')}`  ")
    if report.get("generated_at"):
        timestamp = datetime.fromisoformat(report["generated_at"])
        formatted = timestamp.strftime(
            "%d.%m.%Y %H:%M UTC" if selected == "de" else "%Y-%m-%d %H:%M UTC"
        )
        lines.append(f"**{text['generated_at']}:** {formatted}")
    lines += [
        "",
        f"## {text['counts']}",
        "",
        f"{text['total_cases']}: {format_number(report['total_cases'], selected)}",
        f"{text['evaluated']}: {format_number(report['evaluated'], selected)}",
        "",
    ]
    for key, value in report["counts"].items():
        lines.append(f"- {text['statuses'][key]}: {format_number(value, selected)}")
    lines += [
        "",
        f"## {text['metrics_title']}",
        "",
        f"| {text['metric']} | {text['value']} | {text['fraction']} | {text['excluded']} |",
        "|---|---:|---:|---:|",
    ]
    for key, metric in report["metrics"].items():
        value = (
            text["unmeasured"]
            if metric["value"] is None
            else format_number(metric["value"], selected, percentage=True)
        )
        lines.append(
            f"| {text['metrics'][key]} | {value} | {format_number(metric['numerator'], selected)} / {format_number(metric['denominator'], selected)} | {format_number(metric['excluded'], selected)} |"
        )
    lines += [
        "",
        text["metric_scope"],
        "",
        f"## {text['management']}",
        "",
        text["examined"],
        "",
        text["held"],
        "",
        text["violated"].format(count=report["counts"]["SECURITY_FAILURE"]),
        "",
        text["untested"],
        "",
        text["priority"],
        "",
        f"## {text['findings']}",
        "",
    ]
    failures = [r for r in report["results"] if r["status"] == "SECURITY_FAILURE"]
    lines += [
        f"- `{r['test_id']}`: `{r['family']}` / {', '.join(r['reason_codes'])}" for r in failures
    ]
    if not failures:
        lines.append(text["none"])
    lines += ["", f"## {text['limits']}", ""]
    lines += [f"- `{code}`" for code in report["known_limitations"]]
    original = report["original_observations"]
    lines += [
        "",
        text["original"].format(
            evaluable=original["evaluable"],
            success=original["successful_tool_objectives"],
            tools=original["tool_proposals"],
        ),
        "",
        text["interpretation"],
        "",
        text["hypothesis"],
        "",
    ]
    return "\n".join(lines)


def write_report(report: dict[str, Any], output: Path, locale: str | None = None) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, content in (
        ("report.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n"),
        ("report.md", markdown_report(report, locale)),
    ):
        path = output / name
        staged = output / (name + ".part")
        staged.write_text(content, encoding="utf8")
        staged.replace(path)
