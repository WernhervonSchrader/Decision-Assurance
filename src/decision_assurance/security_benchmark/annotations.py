from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .contracts import MAX_RECORD_BYTES


def object_items(path: Path) -> Iterator[tuple[str, dict[str, Any]]]:
    """Stream the original JSON object without loading its hundreds of MB into RAM."""
    decoder = json.JSONDecoder()
    with path.open(encoding="utf8") as stream:
        buffer = ""
        eof = False

        def refill() -> None:
            nonlocal buffer, eof
            chunk = stream.read(65536)
            if not chunk:
                eof = True
            buffer += chunk
            if len(buffer) > MAX_RECORD_BYTES:
                raise ValueError("ANNOTATION_RECORD_TOO_LARGE")

        def whitespace() -> None:
            nonlocal buffer
            while True:
                buffer = buffer.lstrip()
                if buffer or eof:
                    return
                refill()

        def decode() -> Any:
            nonlocal buffer
            while True:
                whitespace()
                try:
                    value, end = decoder.raw_decode(buffer)
                    buffer = buffer[end:]
                    return value
                except json.JSONDecodeError:
                    if eof:
                        raise ValueError("ANNOTATION_JSON_INVALID") from None
                    refill()

        whitespace()
        if not buffer.startswith("{"):
            raise ValueError("ANNOTATION_OBJECT_REQUIRED")
        buffer = buffer[1:]
        first = True
        while True:
            whitespace()
            if buffer.startswith("}"):
                buffer = buffer[1:]
                whitespace()
                if buffer or stream.read(1):
                    raise ValueError("ANNOTATION_TRAILING_DATA")
                return
            if not first:
                if not buffer.startswith(","):
                    raise ValueError("ANNOTATION_SEPARATOR_REQUIRED")
                buffer = buffer[1:]
            key = decode()
            whitespace()
            if not buffer.startswith(":"):
                raise ValueError("ANNOTATION_COLON_REQUIRED")
            buffer = buffer[1:]
            value = decode()
            if not isinstance(key, str) or not isinstance(value, dict):
                raise ValueError("ANNOTATION_SCHEMA_INVALID")
            yield key, value
            first = False


def annotation_key(subject: str, body: str) -> str:
    return hashlib.sha256(f"Subject of the email: {subject}.   Body: {body}".encode()).hexdigest()


def annotate_index(index: Path, paths: list[Path]) -> dict[str, Any]:
    """Join original attack-attempt labels, independently of raw success objectives."""
    from .dataset import _file_hash

    with sqlite3.connect(index) as db:
        columns = {r[1] for r in db.execute("PRAGMA table_info(records)")}
        for column, datatype in (
            ("annotation_key_sha", "TEXT"),
            ("attack_ground_truth", "INTEGER"),
            ("source_attack_label", "TEXT"),
        ):
            if column not in columns:
                db.execute(f"ALTER TABLE records ADD COLUMN {column} {datatype}")
        db.execute("CREATE INDEX IF NOT EXISTS annotation_join ON records(annotation_key_sha)")
        for file in db.execute("SELECT path FROM files").fetchall():
            with Path(file[0]).open("rb") as stream:
                rows = db.execute(
                    "SELECT content_sha256,offset,length FROM records WHERE path=? AND annotation_key_sha IS NULL ORDER BY offset",
                    (file[0],),
                )
                count = 0
                for content_sha, offset, length in rows:
                    stream.seek(offset)
                    record = json.loads(stream.read(length))
                    db.execute(
                        "UPDATE records SET annotation_key_sha=? WHERE content_sha256=?",
                        (annotation_key(record["subject"], record["body"]), content_sha),
                    )
                    count += 1
                    if count % 1000 == 0:
                        db.commit()
            db.commit()
        db.execute(
            "CREATE TABLE IF NOT EXISTS annotation_files(path TEXT PRIMARY KEY,sha TEXT,count INTEGER)"
        )
        for path in paths:
            sha = _file_hash(path)
            prior = db.execute(
                "SELECT sha FROM annotation_files WHERE path=?", (str(path.resolve()),)
            ).fetchone()
            if prior:
                if prior[0] != sha:
                    raise ValueError("ANNOTATION_SOURCE_CHANGED")
                continue
            count = 0
            for key, value in object_items(path):
                attempted = value.get("attack_attempt")
                label = {
                    k: value[k]
                    for k in ("attack_attempt", "reason", "judge_category")
                    if k in value
                }
                truth = (
                    1
                    if attempted in ("True", True)
                    else 0
                    if attempted in ("False", False)
                    else None
                )
                join_hash = hashlib.sha256(key.encode()).hexdigest()
                previous = db.execute(
                    "SELECT attack_ground_truth,source_attack_label FROM records WHERE annotation_key_sha=?",
                    (join_hash,),
                ).fetchone()
                if previous and previous[1]:
                    prior_label = json.loads(previous[1])
                    if prior_label.get("attack_attempt") == "CONFLICT" or (
                        previous[0] is not None and truth is not None and previous[0] != truth
                    ):
                        truth = None
                        label = {
                            "attack_attempt": "CONFLICT",
                            "reason": "cross_phase_label_conflict",
                        }
                db.execute(
                    "UPDATE records SET attack_ground_truth=?,source_attack_label=? WHERE annotation_key_sha=?",
                    (truth, json.dumps(label), join_hash),
                )
                count += 1
            db.execute(
                "INSERT INTO annotation_files VALUES(?,?,?)", (str(path.resolve()), sha, count)
            )
            db.commit()
        counts = dict(
            db.execute(
                "SELECT COALESCE(CAST(attack_ground_truth AS TEXT),'unknown'),COUNT(*) FROM records GROUP BY attack_ground_truth"
            )
        )
        return {
            "annotation_counts": counts,
            "annotation_files": [
                {"path": Path(row[0]).name, "sha256": row[1], "count": row[2]}
                for row in db.execute("SELECT * FROM annotation_files")
            ],
        }
