from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_packaged_schemas_match_public_schemas() -> None:
    public = ROOT / "schemas"
    packaged = ROOT / "src" / "decision_assurance" / "schemas"
    for schema in public.glob("*.json"):
        assert (packaged / schema.name).read_bytes() == schema.read_bytes()


def test_packaged_migration_matches_public_migration() -> None:
    public = ROOT / "migrations" / "001_api_v0_2.sql"
    packaged = ROOT / "src" / "decision_assurance" / "migrations" / public.name
    assert packaged.read_bytes() == public.read_bytes()


def test_documentation_relative_links_resolve() -> None:
    import re

    for document in [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]:
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
            if "://" not in target and not target.startswith("#"):
                assert (document.parent / target.split("#", 1)[0]).resolve().exists(), (
                    f"broken link in {document}: {target}"
                )
