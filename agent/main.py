import dotenv
from strands import Agent
from strands.models.openai import OpenAIModel

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .tools import (
    create_git_branch,
    create_git_commit,
    git_push,
    git_status,
    list_ansible_playbooks,
    list_git_commits,
    run_ansible_playbook,
)

dotenv.load_dotenv()

model = OpenAIModel(
    client_args={
        "api_key": OPENAI_API_KEY,
    },
    model_id=OPENAI_MODEL,
)

agent = Agent(
    model=model,
    tools=[
        create_git_branch,
        create_git_commit,
        git_push,
        git_status,
        list_ansible_playbooks,
        list_git_commits,
        run_ansible_playbook,
    ],
)
response = agent("Is hello-workers.yaml working?")
print(response)
