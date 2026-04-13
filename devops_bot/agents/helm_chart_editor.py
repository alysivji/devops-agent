from pathlib import Path

from pydantic import BaseModel, Field

from ..factory import build_agent, build_model

SYSTEM_PROMPT = """
You edit existing Helm charts for this repository.

Output Requirements:
- Return only the structured response fields.
- Return complete file contents for every chart file you edit.
- Keep unrelated chart behavior unchanged.
- Keep edits scoped to the chart path provided by the tool prompt.
- Do not invent files outside the chart.
- Keep templates valid YAML/Helm templates.

Editing Rules:
- Make the smallest practical chart change that satisfies the request.
- Prefer values.yaml for user-configurable knobs and templates for Kubernetes
  resources.
- Preserve existing helper template naming conventions in _helpers.tpl.
- For schedulable application workloads, prefer Kubernetes-native deployment,
  service, ingress, config, and secret templates over Ansible wrappers.
- Do not hardcode real secrets or secret-looking sample values. Prefer values
  placeholders and document required values in chart comments only when needed.
- Include validation-relevant changes together. For example, if a deployment
  selector changes, update matching service selectors and labels in the same
  edit.
"""


class HelmChartFileEdit(BaseModel):
    path: str = Field(description="Relative file path inside the chart.")
    content: str = Field(description="Complete edited file content.")


class EditedHelmChart(BaseModel):
    files: list[HelmChartFileEdit] = Field(description="Files to write inside the chart.")
    summary: str = Field(description="Short summary of the chart edit.")
    requires_cluster_validation: bool = Field(
        description="Whether validating the edit requires a live cluster rollout or status check."
    )


class EditHelmChartAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(model_id="gpt-5.4"),
            system_prompt=SYSTEM_PROMPT,
        )

    def run(
        self,
        *,
        chart_path: Path,
        current_files: dict[str, str],
        requested_change: str,
    ) -> EditedHelmChart:
        prompt = build_chart_edit_prompt(
            chart_path=chart_path,
            current_files=current_files,
            requested_change=requested_change,
        )
        return self.agent.structured_output(EditedHelmChart, prompt)


def build_chart_edit_prompt(
    *,
    chart_path: Path,
    current_files: dict[str, str],
    requested_change: str,
) -> str:
    file_sections = []
    for relative_path, content in sorted(current_files.items()):
        file_sections.append(f"Path: {relative_path}\n```yaml\n{content.rstrip()}\n```")
    files_text = "\n\n".join(file_sections)

    return f"""\
Edit this existing Helm chart.

Chart path: {chart_path}

Requested change:
{requested_change.strip()}

Current chart files:
{files_text}
"""
