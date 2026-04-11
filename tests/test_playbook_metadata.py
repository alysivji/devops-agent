from agent.playbook_metadata import SYSTEM_PROMPT, GeneratedPlaybookMetadata


def test_metadata_prompt_requests_medium_one_line_description() -> None:
    assert "medium-sized one-line description" in SYSTEM_PROMPT
    assert "25-45 words" in SYSTEM_PROMPT
    assert "main\n  action, target scope" in SYSTEM_PROMPT
    assert "validation or rollback" in SYSTEM_PROMPT
    assert "without Markdown, bullets, or newlines" in SYSTEM_PROMPT


def test_metadata_schema_documents_medium_description() -> None:
    description_schema = GeneratedPlaybookMetadata.model_json_schema()["properties"]["description"][
        "description"
    ]

    assert "Medium-sized one-line summary" in description_schema
    assert "25-45 words" in description_schema
    assert "validation or safety behavior" in description_schema


def test_metadata_prompt_requires_conservative_approval_for_remote_changes() -> None:
    assert "requires_approval: true" in SYSTEM_PROMPT
    assert "remote changes" in SYSTEM_PROMPT
    assert "privilege escalation" in SYSTEM_PROMPT
    assert "restart services" in SYSTEM_PROMPT
    assert "Use `false` only for low-risk local inspection" in SYSTEM_PROMPT
