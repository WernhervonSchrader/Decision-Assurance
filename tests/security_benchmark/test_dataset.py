import hashlib
import json
from pathlib import Path

import httpx
import pytest

from decision_assurance.security_benchmark.dataset import (
    acquire_file,
    build_index,
    scan_payloads,
    select_records,
    verify_file,
)


def test_content_triage_handles_long_untrusted_tokens_without_emitting_them(tmp_path: Path) -> None:
    path = tmp_path / "long.jsonl"
    path.write_text(
        json.dumps({"RowKey": "long", "subject": "", "body": "A" * 128000, "scenario": "level1a"})
        + "\n"
    )
    result = scan_payloads(path)
    assert result["records"] == 1
    assert result["flags"] == {"credential_shaped": 0, "email_address": 0, "active_content": 0}
    assert result["publication_approved"] is False


def raw_fixture(path: Path, count: int = 80) -> Path:
    with path.open("wb") as stream:
        for i in range(count):
            stream.write(
                (
                    json.dumps(
                        {
                            "RowKey": str(i),
                            "subject": "Data only",
                            "body": f"Original {i % 60}\nUnicode: ä",
                            "scenario": f"level{i % 4 + 1}a",
                            "objectives": json.dumps(
                                {
                                    "email.retrieved": True,
                                    "defense.undetected": True,
                                    "exfil.sent": False,
                                    "exfil.destination": False,
                                    "exfil.content": False,
                                }
                            ),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                ).encode()
            )
    return path


def test_raw_bytes_are_preserved_and_checksum_mismatch_fails(tmp_path: Path) -> None:
    raw = raw_fixture(tmp_path / "raw.jsonl")
    original = raw.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    verify_file(raw, digest, len(original))
    with pytest.raises(ValueError, match="CHECKSUM"):
        verify_file(raw, "0" * 64, len(original))
    build_index([raw], tmp_path / "index.sqlite")
    assert raw.read_bytes() == original


def test_stratified_sampling_is_stable_and_dedup_is_separate(tmp_path: Path) -> None:
    raw = raw_fixture(tmp_path / "raw.jsonl")
    index = tmp_path / "index.sqlite"
    summary = build_index([raw], index)
    assert summary["raw_records"] == 80
    assert summary["unique_payloads"] == 60
    a = select_records(index, 20, 42)
    assert a == select_records(index, 20, 42)
    assert a != select_records(index, 20, 43)
    assert len({x["content_sha256"] for x in a}) == 20
    assert len({x["scenario"] for x in a}) == 4
    with pytest.raises(ValueError, match="INSUFFICIENT"):
        select_records(index, 100, 42)


def test_download_rejects_redirect_outside_exact_sources(tmp_path: Path) -> None:
    def response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://attacker.example/payload"})

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(ValueError, match="SOURCE"):
            acquire_file(
                client,
                "https://huggingface.co/datasets/microsoft/llmail-inject-challenge/resolve/"
                + "a" * 40
                + "/data/x.jsonl",
                tmp_path / "raw",
                "0" * 64,
                1,
            )
    assert not (tmp_path / "raw").exists()


def test_invalid_jsonl_is_not_silently_dropped(tmp_path: Path) -> None:
    raw = tmp_path / "bad.jsonl"
    raw.write_text("{broken}\n", encoding="utf8")
    with pytest.raises(ValueError, match="RAW_RECORD"):
        build_index([raw], tmp_path / "index.sqlite")


def test_checkpoint_cannot_hide_changed_raw_bytes(tmp_path: Path) -> None:
    raw = raw_fixture(tmp_path / "raw.jsonl")
    index = tmp_path / "index.sqlite"
    build_index([raw], index)
    raw.write_bytes(raw.read_bytes().replace(b"Original", b"Modified", 1))
    with pytest.raises(ValueError, match="RAW_CHANGED"):
        select_records(index, 10, 42)


def test_download_resumes_exact_bytes_and_checks_range(tmp_path: Path) -> None:
    data = b"0123456789"
    path = tmp_path / "raw"
    path.with_suffix(".part").write_bytes(data[:4])

    def response(request: httpx.Request) -> httpx.Response:
        assert request.headers["range"] == "bytes=4-9"
        return httpx.Response(206, headers={"Content-Range": "bytes 4-9/10"}, content=data[4:])

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        acquire_file(
            client, "https://huggingface.co/data", path, hashlib.sha256(data).hexdigest(), len(data)
        )
    assert path.read_bytes() == data
    path.unlink()
    path.with_suffix(".part").write_bytes(data[:4])
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                206, headers={"Content-Range": "bytes 5-9/10"}, content=data[5:]
            )
        )
    ) as client:
        with pytest.raises(ValueError, match="RANGE"):
            acquire_file(
                client,
                "https://huggingface.co/data",
                path,
                hashlib.sha256(data).hexdigest(),
                len(data),
            )


def test_index_resume_preserves_prefix_and_rejects_extra_sources(tmp_path: Path) -> None:
    raw = raw_fixture(tmp_path / "raw.jsonl", 20)
    index = tmp_path / "index.sqlite"
    summary = build_index([raw], index, batch_size=2)
    assert summary == build_index([raw], index, batch_size=2)
    other = raw_fixture(tmp_path / "other.jsonl", 5)
    with pytest.raises(ValueError, match="SOURCE_SET"):
        build_index([other], index)
