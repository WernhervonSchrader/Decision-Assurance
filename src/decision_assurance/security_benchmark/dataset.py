from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from .contracts import MAX_RECORD_BYTES, ROOT, digest, read_json, safe_child

LOCK_PATH = ROOT / "benchmarks/security/datasets/llmail/source-lock.json"
DOWNLOAD_HOSTS = frozenset(
    {
        "huggingface.co",
        "cas-bridge.xethub.hf.co",
        "cdn-lfs.hf.co",
        "cdn-lfs-us-1.hf.co",
        "cdn-lfs-eu-1.hf.co",
        "us.aws.cdn.hf.co",
    }
)
CATEGORIES = {
    "instruction_override": ("ignore previous", "ignore all", "disregard"),
    "authority_spoofing": ("system instruction", "administrator", "authorized by"),
    "role_spoofing": ("<|assistant|>", "[system]", "you are now"),
    "tool_output_injection": ("tool result", "tool output", "api_call"),
    "retrieved_document_injection": ("retrieved document", "search result"),
    "data_exfiltration": ("exfiltrat", "q2 budget", "profit forecast"),
    "workflow_hijacking": ("send an email", "send email", "send a confirmation"),
    "context_manipulation": ("end_user", "context window", "end of context"),
    "encoded_payload": ("base64", "decode", "rot13"),
    "benign_malicious_mixing": ("summary", "summariz", "summarise"),
}


def classify(subject: str, body: str) -> list[str]:
    """Versioned project heuristics, never original Microsoft attack labels."""
    text = (subject + "\n" + body).casefold()
    return [name for name, words in CATEGORIES.items() if any(w in text for w in words)] or [
        "unclassified"
    ]


def verify_file(path: Path, expected_sha256: str, expected_size: int) -> None:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(MAX_RECORD_BYTES), b""):
            hasher.update(chunk)
            size += len(chunk)
    if size != expected_size or hasher.hexdigest() != expected_sha256:
        raise ValueError("DATASET_CHECKSUM_MISMATCH")


def _safe_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in DOWNLOAD_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("DOWNLOAD_SOURCE_REJECTED")


def acquire_file(client: httpx.Client, url: str, target: Path, sha256: str, size: int) -> None:
    """Only explicit acquisition can use HTTP; redirects rechecked before each request."""
    if target.exists():
        verify_file(target, sha256, size)
        return
    temporary = target.with_suffix(target.suffix + ".part")
    target.parent.mkdir(parents=True, exist_ok=True)
    origin = url
    chunk_size = 32 * MAX_RECORD_BYTES
    maximum_requests = (size // chunk_size + 1) * 4
    failures = 0
    for _request in range(maximum_requests):
        url = origin
        try:
            for _ in range(6):
                _safe_url(url)
                offset = temporary.stat().st_size if temporary.exists() else 0
                if offset == size:
                    verify_file(temporary, sha256, size)
                    temporary.replace(target)
                    return
                if offset > size:
                    raise ValueError("DOWNLOAD_SIZE_EXCEEDED")
                end = min(size - 1, offset + chunk_size - 1)
                request_headers = {"Range": f"bytes={offset}-{end}"}
                with client.stream(
                    "GET", url, headers=request_headers, follow_redirects=False
                ) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers["location"])
                        continue
                    response.raise_for_status()
                    if response.status_code == 206:
                        content_range = response.headers.get("content-range", "")
                        if not content_range.startswith(
                            f"bytes {offset}-"
                        ) or not content_range.endswith(f"/{size}"):
                            raise ValueError("DOWNLOAD_RANGE_MISMATCH")
                        mode = "ab"
                    elif response.status_code == 200:
                        offset, mode = 0, "wb"
                    else:
                        raise ValueError("DOWNLOAD_RESPONSE_INVALID")
                    received = offset
                    with temporary.open(mode) as stream:
                        for chunk in response.iter_bytes(MAX_RECORD_BYTES):
                            received += len(chunk)
                            if received > size:
                                raise ValueError("DOWNLOAD_SIZE_EXCEEDED")
                            stream.write(chunk)
                if temporary.stat().st_size == size:
                    verify_file(temporary, sha256, size)
                    temporary.replace(target)
                    return
                if temporary.stat().st_size <= offset:
                    raise ValueError("DOWNLOAD_NO_PROGRESS")
                failures = 0
                break
            else:
                raise ValueError("DOWNLOAD_REDIRECT_LIMIT")
        except httpx.TransportError:
            failures += 1
            if failures == 4:
                raise ValueError("DOWNLOAD_TRANSPORT_FAILED") from None
            time.sleep(min(2 ** (failures - 1), 4))
    raise ValueError("DOWNLOAD_REQUEST_LIMIT")


def acquire_dataset(output: Path, *, include_annotations: bool = False) -> dict[str, Any]:
    lock = read_json(LOCK_PATH)
    with httpx.Client(timeout=httpx.Timeout(90, connect=30), trust_env=False) as client:
        for item in lock["files"]:
            if item["kind"] == "annotations" and not include_annotations:
                continue
            target = safe_child(output, item["path"])
            url = f"https://huggingface.co/datasets/microsoft/llmail-inject-challenge/resolve/{lock['revision']}/{item['path']}?download=true"
            acquire_file(client, url, target, item["sha256"], item["size"])
    manifest = {
        "schema_version": "0.1",
        "revision": lock["revision"],
        "lock_sha256": digest(lock),
        "files": [x for x in lock["files"] if include_annotations or x["kind"] != "annotations"],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    return manifest


def _raw_rows(path: Path, start: int = 0) -> Iterator[tuple[int, int, dict[str, Any], str]]:
    with path.open("rb") as stream:
        stream.seek(start)
        while True:
            offset = stream.tell()
            raw = stream.readline(MAX_RECORD_BYTES + 1)
            if not raw:
                return
            if len(raw) > MAX_RECORD_BYTES:
                raise ValueError("RAW_RECORD_TOO_LARGE")
            try:
                record = json.loads(raw)
                if not isinstance(record, dict) or not all(
                    isinstance(record.get(k), str)
                    for k in ("RowKey", "subject", "body", "scenario")
                ):
                    raise ValueError("RAW_RECORD_SCHEMA")
            except (ValueError, UnicodeDecodeError) as error:
                raise ValueError(f"RAW_RECORD_INVALID:{offset}") from error
            yield offset, len(raw), record, hashlib.sha256(raw).hexdigest()


def _file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(MAX_RECORD_BYTES), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_index(raw_paths: list[Path], index: Path, *, batch_size: int = 1000) -> dict[str, Any]:
    """Resumable derived SQLite index; raw bytes and duplicate submissions stay intact."""
    if not raw_paths or batch_size < 1:
        raise ValueError("INDEX_INPUT_REQUIRED")
    index.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(index) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, sha TEXT, size INTEGER,
                cursor INTEGER DEFAULT 0, count INTEGER DEFAULT 0, complete INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS records(content_sha256 TEXT PRIMARY KEY, source_record_id TEXT,
                scenario TEXT, categories TEXT, stratum TEXT, path TEXT, offset INTEGER,
                length INTEGER, raw_sha256 TEXT, original_result TEXT);
        """)
        supplied = {str(p.resolve()) for p in raw_paths}
        existing = {r[0] for r in db.execute("SELECT path FROM files")}
        if existing - supplied:
            raise ValueError("INDEX_SOURCE_SET_CHANGED")
        for path in raw_paths:
            name, sha, size = str(path.resolve()), _file_hash(path), path.stat().st_size
            previous = db.execute(
                "SELECT sha,size,cursor,count,complete FROM files WHERE path=?", (name,)
            ).fetchone()
            if previous and previous[:2] != (sha, size):
                raise ValueError("INDEX_RAW_CHANGED")
            if previous and previous[4]:
                continue
            db.execute(
                "INSERT OR IGNORE INTO files(path,sha,size) VALUES(?,?,?)", (name, sha, size)
            )
            start, count = (previous[2], previous[3]) if previous else (0, 0)
            for offset, length, record, raw_sha in _raw_rows(path, start):
                content_sha = digest({"subject": record["subject"], "body": record["body"]})
                categories = classify(record["subject"], record["body"])
                original = record.get("objectives")
                if isinstance(original, str):
                    try:
                        original = json.loads(original)
                    except ValueError:
                        original = None
                db.execute(
                    "INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        content_sha,
                        record["RowKey"],
                        record["scenario"],
                        json.dumps(categories),
                        record["scenario"] + ":" + categories[0],
                        name,
                        offset,
                        length,
                        raw_sha,
                        json.dumps(original),
                    ),
                )
                count += 1
                db.execute(
                    "UPDATE files SET cursor=?,count=? WHERE path=?", (offset + length, count, name)
                )
                if count % batch_size == 0:
                    db.commit()
            db.execute("UPDATE files SET complete=1 WHERE path=?", (name,))
            db.commit()
        return {
            "raw_records": db.execute("SELECT SUM(count) FROM files").fetchone()[0],
            "unique_payloads": db.execute("SELECT COUNT(*) FROM records").fetchone()[0],
            "strata": db.execute("SELECT COUNT(DISTINCT stratum) FROM records").fetchone()[0],
        }


def select_records(index: Path, count: int, seed: int) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("SAMPLE_COUNT_INVALID")
    with sqlite3.connect(index) as db:
        db.row_factory = sqlite3.Row
        for file in db.execute("SELECT * FROM files"):
            if not file["complete"] or _file_hash(Path(file["path"])) != file["sha"]:
                raise ValueError("INDEX_RAW_CHANGED_OR_INCOMPLETE")
        db.create_function(
            "seed_rank",
            1,
            lambda value: hashlib.sha256(f"{seed}:{value}".encode()).hexdigest(),
            deterministic=True,
        )
        rows = db.execute(
            """SELECT * FROM (SELECT *, ROW_NUMBER() OVER
            (PARTITION BY stratum ORDER BY seed_rank(content_sha256), content_sha256) AS rank
            FROM records) ORDER BY rank,stratum,content_sha256 LIMIT ?""",
            (count,),
        ).fetchall()
        if len(rows) != count:
            raise ValueError("INSUFFICIENT_UNIQUE_RECORDS")
        return [{k: row[k] for k in row.keys() if k != "rank"} for row in rows]


def read_payload(reference: dict[str, Any], root: Path) -> dict[str, Any]:
    path = safe_child(root, reference["path"])
    if reference["length"] > MAX_RECORD_BYTES:
        raise ValueError("PAYLOAD_TOO_LARGE")
    with path.open("rb") as stream:
        stream.seek(reference["offset"])
        raw = stream.read(reference["length"])
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("PAYLOAD_CHECKSUM_MISMATCH")
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise ValueError("PAYLOAD_OBJECT_REQUIRED")
    return record


def scan_payloads(path: Path) -> dict[str, Any]:
    """Aggregate review aid only; no payloads or extracted identifiers are emitted."""
    import re

    patterns = {
        "credential_shaped": r"(?i)(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY|(?:password|api[_-]?key)\s*[:=]\s*[^\s]{8,})",
        "email_address": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "active_content": r"(?i)(?:<script|javascript:|powershell|/bin/(?:ba)?sh|eval\()",
    }
    counts = dict.fromkeys(patterns, 0)
    records = 0
    for _, _, record, _ in _raw_rows(path):
        text = record["subject"] + "\n" + record["body"]
        records += 1
        for name, pattern in patterns.items():
            counts[name] += bool(re.search(pattern, text))
    return {
        "records": records,
        "flags": counts,
        "publication_approved": False,
        "limitation": "Heuristic triage only; independent content review required.",
    }
