from pydantic import BaseModel, Field

from ..factory import build_agent, build_model

SYSTEM_PROMPT = """
You edit this repository's .env.example file.

Rules:
- Return only the structured response fields.
- Return the complete edited .env.example file content.
- Preserve existing content, comments, ordering, and section header style unless
  a small move is needed to place new variables in a more sensible existing
  section.
- Add required variables as active placeholder assignments: NAME=placeholder.
- Add optional variables as commented placeholder assignments: # NAME=placeholder.
- Put new variables near related variables or in the most relevant existing
  section. Create a new separated section only when no existing section fits.
- Do not include real secrets or secret-looking generated values.
- Do not remove or rename existing variables.
"""


class EditedEnvExample(BaseModel):
    content: str = Field(description="Complete edited .env.example file content.")


class EnvExampleUpdateAgent:
    def __init__(self) -> None:
        self.agent = build_agent(
            model=build_model(model_id="gpt-4o-mini"),
            system_prompt=SYSTEM_PROMPT,
        )

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
        prompt = build_env_example_update_prompt(
            env_example_content=env_example_content,
            required_variable_names=required_variable_names,
            optional_variable_names=optional_variable_names,
            source_path=source_path,
            section_name=section_name,
            placeholder_value=placeholder_value,
        )
        return self.agent.structured_output(EditedEnvExample, prompt)


def build_env_example_update_prompt(
    *,
    env_example_content: str,
    required_variable_names: list[str],
    optional_variable_names: list[str],
    source_path: str,
    section_name: str,
    placeholder_value: str,
) -> str:
    source_hint = source_path.strip() or "(not provided)"
    section_hint = section_name.strip() or "(choose the best existing section)"
    return f"""\
Update this .env.example file.

Source path that introduced these variables:
{source_hint}

Preferred section:
{section_hint}

Placeholder value:
{placeholder_value}

Required variables to add as active assignments:
{_format_variable_list(required_variable_names)}

Optional variables to add as commented assignments:
{_format_variable_list(optional_variable_names)}

Current .env.example content:
```dotenv
{env_example_content.rstrip()}
```
"""


def _format_variable_list(variable_names: list[str]) -> str:
    if not variable_names:
        return "- (none)"
    return "\n".join(f"- {name}" for name in variable_names)
