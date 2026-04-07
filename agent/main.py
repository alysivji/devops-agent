import dotenv
from strands import Agent
from strands.models.openai import OpenAIModel

from .config import OPENAI_API_KEY, OPENAI_MODEL
from .tools import list_ansible_playbooks, run_ansible_playbook

dotenv.load_dotenv()

model = OpenAIModel(
    client_args={
        "api_key": OPENAI_API_KEY,
    },
    model_id=OPENAI_MODEL,
)

agent = Agent(model=model, tools=[list_ansible_playbooks, run_ansible_playbook])
response = agent("Is hello-workers.yaml working?")
print(response)
