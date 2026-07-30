from pathlib import Path

ROOT = Path(__file__).parents[3]
SKILL = ROOT / "integrations" / "chatgpt-work" / "conduct-assured-web-research"
TOOLS = {
    "research_start",
    "research_get",
    "research_retry",
    "research_cancel",
    "research_handoff",
}


def test_skill_template_contains_only_approved_source_files() -> None:
    actual = {item.relative_to(SKILL).as_posix() for item in SKILL.rglob("*") if item.is_file()}
    assert actual == {
        "SKILL.md",
        "agents/openai.yaml",
        "references/research-modes.md",
        "references/source-policy.md",
        "references/evidence-contract.md",
        "references/tool-contract.md",
    }


def test_skill_is_bounded_to_five_tools_and_has_no_installation_claim() -> None:
    combined = "\n".join(item.read_text(encoding="utf-8") for item in SKILL.rglob("*.md"))
    assert all(f"`{tool}`" in combined for tool in TOOLS)
    for forbidden in ("crawl_anything", "shell_exec", "filesystem", "tenant_id input"):
        assert forbidden not in combined
    assert "already installed" not in combined.casefold()
    assert "untrusted" in combined.casefold()
    assert "human review" in combined.casefold()


def test_openai_yaml_mentions_skill_in_default_prompt() -> None:
    configuration = (SKILL / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert 'display_name: "Conduct Assured Web Research"' in configuration
    assert "$conduct-assured-web-research" in configuration
