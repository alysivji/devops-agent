import os

import dotenv
from strands import Agent
from strands.models.openai import OpenAIModel

from .tools import list_ansible_playbooks, run_ansible_playbook

dotenv.load_dotenv()

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set.")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

model = OpenAIModel(
    client_args={
        "api_key": os.getenv("OPENAI_API_KEY"),
    },
    model_id=OPENAI_MODEL,
)

agent = Agent(model=model, tools=[list_ansible_playbooks, run_ansible_playbook])
response = agent("Is hello-workers.yaml working?")
print(response)
