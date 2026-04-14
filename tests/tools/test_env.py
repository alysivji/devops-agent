from pathlib import Path

import pytest

from devops_bot.agents import env_example_editor as env_example_editor_module
from devops_bot.agents.env_example_editor import EditedEnvExample, EnvExampleUpdateAgent
from devops_bot.tools.env import env_example_update, env_list_loaded_keys


class StubEnvExampleUpdateAgent:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests: list[dict[str, object]] = []

    def run(
        self,
        *,
        env_example_content: str,
        required_variable_names: list[str],
        optional_variable_names: list[str],
        source_path: str,
        section_name: str,
        placeholder_value: str,
    ) -> EditedEnvExample:
        self.requests.append(
            {
                "env_example_content": env_example_content,
                "required_variable_names": required_variable_names,
                "optional_variable_names": optional_variable_names,
                "source_path": source_path,
                "section_name": section_name,
                "placeholder_value": placeholder_value,
            }
        )
        return EditedEnvExample(content=self.content)


def test_env_list_loaded_keys_reports_dotenv_keys_without_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "GRAFANA_ADMIN_USER=admin\nGRAFANA_ADMIN_PASSWORD=super-secret\nEMPTY_VALUE=\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GRAFANA_ADMIN_USER", raising=False)
    monkeypatch.delenv("GRAFANA_ADMIN_PASSWORD", raising=False)

    result = env_list_loaded_keys()

    assert "GRAFANA_ADMIN_USER" in result["loaded_keys"]
    assert "GRAFANA_ADMIN_PASSWORD" in result["loaded_keys"]
    assert "EMPTY_VALUE" not in result["loaded_keys"]
    assert "super-secret" not in str(result)


def test_env_list_loaded_keys_checks_playbook_env_lookups(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    playbook_path = tmp_path / "ansible" / "playbooks" / "install-grafana.yaml"
    playbook_path.parent.mkdir(parents=True)
    playbook_path.write_text(
        (
            "- hosts: control\n"
            "  vars:\n"
            "    grafana_admin_user: \"{{ lookup('ansible.builtin.env', "
            "'GRAFANA_ADMIN_USER', default='') }}\"\n"
            "    grafana_admin_password: \"{{ lookup('ansible.builtin.env', "
            "'GRAFANA_ADMIN_PASSWORD', default='') }}\"\n"
            "    grafana_http_port: \"{{ lookup('ansible.builtin.env', "
            "'GRAFANA_HTTP_PORT', default='3000') }}\"\n"
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("GRAFANA_ADMIN_USER=admin\n", encoding="utf-8")
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "os-secret")
    monkeypatch.delenv("GRAFANA_HTTP_PORT", raising=False)

    result = env_list_loaded_keys(source_path="ansible/playbooks/install-grafana.yaml")

    assert result["loaded_keys"] == ["GRAFANA_ADMIN_PASSWORD", "GRAFANA_ADMIN_USER"]
    assert result["required_variables"] == ["GRAFANA_ADMIN_PASSWORD", "GRAFANA_ADMIN_USER"]
    assert result["optional_variables"] == ["GRAFANA_HTTP_PORT"]
    assert result["present_required"] == ["GRAFANA_ADMIN_PASSWORD", "GRAFANA_ADMIN_USER"]
    assert result["missing_required"] == []
    assert result["present_optional"] == []
    assert result["missing_optional"] == ["GRAFANA_HTTP_PORT"]
    assert "os-secret" not in str(result)


def test_env_example_update_adds_missing_variable_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("OPENAI_API_KEY=your-openai-api-key\n", encoding="utf-8")
    edited_content = (
        "OPENAI_API_KEY=your-openai-api-key\n"
        "\n"
        "#############################\n"
        "# application configuration\n"
        "#############################\n"
        "GRAFANA_ADMIN_PASSWORD=change-me\n"
    )
    stub_editor = StubEnvExampleUpdateAgent(edited_content)
    monkeypatch.setattr("devops_bot.tools.env.EnvExampleUpdateAgent", lambda: stub_editor)

    result = env_example_update("GRAFANA_ADMIN_PASSWORD")

    assert result == {
        "path": ".env.example",
        "variables": ["GRAFANA_ADMIN_PASSWORD"],
        "required_variables": ["GRAFANA_ADMIN_PASSWORD"],
        "optional_variables": [],
        "added": ["GRAFANA_ADMIN_PASSWORD"],
        "already_present": [],
    }
    assert (tmp_path / ".env.example").read_text(encoding="utf-8") == edited_content
    assert stub_editor.requests[0]["required_variable_names"] == ["GRAFANA_ADMIN_PASSWORD"]
    assert stub_editor.requests[0]["optional_variable_names"] == []


def test_env_example_update_scans_ansible_env_lookups(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    playbook_path = tmp_path / "ansible" / "playbooks" / "install-grafana.yaml"
    playbook_path.parent.mkdir(parents=True)
    playbook_path.write_text(
        (
            "- hosts: control\n"
            "  vars:\n"
            "    grafana_admin_password: \"{{ lookup('ansible.builtin.env', "
            "'GRAFANA_ADMIN_PASSWORD', default='') }}\"\n"
            "    grafana_http_port: \"{{ lookup('ansible.builtin.env', "
            "'GRAFANA_HTTP_PORT', default='3000') }}\"\n"
            '    grafana_secret_key: \'{{ lookup("env", "GRAFANA_SECRET_KEY") }}\'\n'
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text(
        (
            "#######################\n"
            "# ansible configuration\n"
            "#######################\n"
            "GRAFANA_ADMIN_PASSWORD=change-me\n"
        ),
        encoding="utf-8",
    )
    edited_content = (
        "#######################\n"
        "# ansible configuration\n"
        "#######################\n"
        "GRAFANA_ADMIN_PASSWORD=change-me\n"
        "\n"
        "GRAFANA_SECRET_KEY=change-me\n"
        "# GRAFANA_HTTP_PORT=change-me\n"
    )
    stub_editor = StubEnvExampleUpdateAgent(edited_content)
    monkeypatch.setattr("devops_bot.tools.env.EnvExampleUpdateAgent", lambda: stub_editor)

    result = env_example_update(source_path="ansible/playbooks/install-grafana.yaml")

    assert result["variables"] == [
        "GRAFANA_ADMIN_PASSWORD",
        "GRAFANA_HTTP_PORT",
        "GRAFANA_SECRET_KEY",
    ]
    assert result["required_variables"] == ["GRAFANA_ADMIN_PASSWORD", "GRAFANA_SECRET_KEY"]
    assert result["optional_variables"] == ["GRAFANA_HTTP_PORT"]
    assert result["added"] == ["GRAFANA_HTTP_PORT", "GRAFANA_SECRET_KEY"]
    assert result["already_present"] == ["GRAFANA_ADMIN_PASSWORD"]
    assert (tmp_path / ".env.example").read_text(encoding="utf-8") == edited_content
    assert stub_editor.requests[0]["required_variable_names"] == ["GRAFANA_SECRET_KEY"]
    assert stub_editor.requests[0]["optional_variable_names"] == ["GRAFANA_HTTP_PORT"]


def test_env_example_update_skips_agent_when_variables_are_already_documented(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    playbook_path = tmp_path / "ansible" / "playbooks" / "install-grafana.yaml"
    playbook_path.parent.mkdir(parents=True)
    playbook_path.write_text(
        (
            "- hosts: control\n"
            "  vars:\n"
            "    grafana_admin_password: \"{{ lookup('ansible.builtin.env', "
            "'GRAFANA_ADMIN_PASSWORD', default='') }}\"\n"
            "    grafana_http_port: \"{{ lookup('ansible.builtin.env', "
            "'GRAFANA_HTTP_PORT', default='3000') }}\"\n"
        ),
        encoding="utf-8",
    )
    env_example_content = (
        "#######################\n"
        "# ansible configuration\n"
        "#######################\n"
        "GRAFANA_ADMIN_PASSWORD=change-me\n"
        "# GRAFANA_HTTP_PORT=change-me\n"
    )
    (tmp_path / ".env.example").write_text(env_example_content, encoding="utf-8")

    def fail_if_called() -> StubEnvExampleUpdateAgent:
        raise AssertionError("env editor agent should not run when all variables are documented")

    monkeypatch.setattr("devops_bot.tools.env.EnvExampleUpdateAgent", fail_if_called)

    result = env_example_update(source_path="ansible/playbooks/install-grafana.yaml")

    assert result["added"] == []
    assert result["already_present"] == ["GRAFANA_ADMIN_PASSWORD", "GRAFANA_HTTP_PORT"]
    assert (tmp_path / ".env.example").read_text(encoding="utf-8") == env_example_content


def test_env_example_update_rejects_invalid_variable_names(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="invalid environment variable names"):
        env_example_update("grafana-password")


def test_env_example_update_agent_uses_simple_model(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_build_agent(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(env_example_editor_module, "build_model", lambda model_id: model_id)
    monkeypatch.setattr(env_example_editor_module, "build_agent", fake_build_agent)

    EnvExampleUpdateAgent()

    assert captured["model"] == "gpt-4o-mini"
