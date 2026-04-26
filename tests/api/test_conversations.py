from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command

from apps.api.conversations.models import (
    ApprovalStatus,
    Conversation,
    ConversationStatus,
    Event,
    Job,
    JobStatus,
    Message,
    MessageRole,
    PendingApproval,
)
from apps.api.conversations.services import (
    ActiveConversationExistsError,
    approve_pending_approval,
    create_conversation,
    enqueue_conversation_job,
    run_job,
    submit_conversation_message,
)
from apps.api.conversations.tasks import run_conversation_job
from devops_bot.approval import WaitingForApproval
from devops_bot.workflow import WorkflowResult


class _AsyncResult:
    def __init__(self, task_id: str) -> None:
        self.id = task_id


class SuccessfulConversationRunner:
    def __init__(self, *, session_id: str | None = None) -> None:
        self.session_id = session_id

    def run(self, prompt: str, *, event_sink, approval_resolver) -> WorkflowResult:
        event_sink({"kind": "run_started", "prompt": prompt})
        event_sink({"kind": "message", "role": "agent", "text": "done"})
        return WorkflowResult(status="completed", response=f"completed: {prompt}")


class FailingConversationRunner:
    def __init__(self, *, session_id: str | None = None) -> None:
        self.session_id = session_id

    def run(self, prompt: str, *, event_sink, approval_resolver) -> WorkflowResult:
        event_sink({"kind": "run_failed", "text": "boom"})
        return WorkflowResult(status="failed", error="boom")


class ApprovalConversationRunner:
    def __init__(self, *, session_id: str | None = None) -> None:
        self.session_id = session_id

    def run(self, prompt: str, *, event_sink, approval_resolver) -> WorkflowResult:
        event_sink({"kind": "run_started", "prompt": prompt})
        try:
            approval_resolver(
                {
                    "kind": "confirmation",
                    "prompt": "Approve deployment?",
                    "context": {"path": "ansible/playbooks/hello-local-test.yaml"},
                }
            )
        except WaitingForApproval as exc:
            return WorkflowResult(status="paused_for_approval", approval_request=exc.request)
        return WorkflowResult(status="completed", response=f"approved: {prompt}")


@pytest.fixture(autouse=True)
def eager_celery(settings) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = True


@pytest.fixture
def fake_delay(monkeypatch):
    counter = {"value": 0}

    def _delay(job_id: int) -> _AsyncResult:
        counter["value"] += 1
        return _AsyncResult(f"task-{job_id}-{counter['value']}")

    monkeypatch.setattr("apps.api.conversations.tasks.run_conversation_job.delay", _delay)
    return _delay


@pytest.mark.django_db
def test_create_conversation_enforces_single_active_conversation(fake_delay) -> None:
    create_conversation(prompt="first")

    with pytest.raises(ActiveConversationExistsError) as exc:
        create_conversation(prompt="second")

    assert exc.value.conversation.initial_prompt == "first"


@pytest.mark.django_db
def test_run_job_marks_conversation_completed() -> None:
    conversation = Conversation.objects.create(initial_prompt="test prompt", session_id="session-1")
    message = Message.objects.create(
        conversation=conversation,
        role=MessageRole.USER,
        text="test prompt",
    )
    job = Job.objects.create(
        conversation=conversation,
        request_message=message,
        submitted_payload={"prompt": "test prompt"},
    )

    result = run_job(job.id, agent_factory=SuccessfulConversationRunner)

    conversation.refresh_from_db()
    job.refresh_from_db()

    assert result.status == "completed"
    assert conversation.status == ConversationStatus.COMPLETED
    assert conversation.final_summary == "completed: test prompt"
    assert job.status == JobStatus.COMPLETED
    assert Event.objects.filter(conversation=conversation, job=job, kind="message").exists()
    assert conversation.messages.filter(
        role=MessageRole.ASSISTANT,
        text="completed: test prompt",
    ).exists()


@pytest.mark.django_db
def test_run_job_marks_conversation_failed() -> None:
    conversation = Conversation.objects.create(initial_prompt="test prompt", session_id="session-2")
    message = Message.objects.create(
        conversation=conversation,
        role=MessageRole.USER,
        text="test prompt",
    )
    job = Job.objects.create(
        conversation=conversation,
        request_message=message,
        submitted_payload={"prompt": "test prompt"},
    )

    result = run_job(job.id, agent_factory=FailingConversationRunner)

    conversation.refresh_from_db()
    job.refresh_from_db()

    assert result.status == "failed"
    assert conversation.status == ConversationStatus.FAILED
    assert conversation.error_text == "boom"
    assert job.status == JobStatus.FAILED
    assert job.error_text == "boom"
    assert conversation.messages.filter(role=MessageRole.ERROR, text="boom").exists()


@pytest.mark.django_db
def test_run_job_persists_pending_approval() -> None:
    conversation = Conversation.objects.create(initial_prompt="deploy", session_id="session-3")
    message = Message.objects.create(
        conversation=conversation,
        role=MessageRole.USER,
        text="deploy",
    )
    job = Job.objects.create(
        conversation=conversation,
        request_message=message,
        submitted_payload={"prompt": "deploy"},
    )

    result = run_job(job.id, agent_factory=ApprovalConversationRunner)

    conversation.refresh_from_db()
    job.refresh_from_db()
    pending_approval = PendingApproval.objects.get(conversation=conversation, job=job)

    assert result.status == "paused_for_approval"
    assert conversation.status == ConversationStatus.WAITING_FOR_APPROVAL
    assert job.status == JobStatus.WAITING_FOR_APPROVAL
    assert pending_approval.status == ApprovalStatus.PENDING
    assert pending_approval.prompt == "Approve deployment?"


@pytest.mark.django_db
def test_approve_pending_approval_enqueues_resume_job(fake_delay) -> None:
    conversation = Conversation.objects.create(
        initial_prompt="deploy",
        session_id="session-4",
        status=ConversationStatus.WAITING_FOR_APPROVAL,
    )
    message = Message.objects.create(
        conversation=conversation,
        role=MessageRole.USER,
        text="deploy",
    )
    original_job = Job.objects.create(
        conversation=conversation,
        request_message=message,
        status=JobStatus.WAITING_FOR_APPROVAL,
        submitted_payload={"prompt": "deploy"},
    )
    pending_approval = PendingApproval.objects.create(
        conversation=conversation,
        job=original_job,
        kind="confirmation",
        prompt="Approve deployment?",
        action_payload={"path": "ansible/playbooks/hello-local-test.yaml"},
    )

    job = approve_pending_approval(pending_approval)

    pending_approval.refresh_from_db()
    conversation.refresh_from_db()
    assert pending_approval.status == ApprovalStatus.APPROVED
    assert conversation.status == ConversationStatus.QUEUED
    assert job.kind == "approval_resume"
    assert job.submitted_payload["pending_approval_id"] == pending_approval.id


@pytest.mark.django_db
def test_enqueue_conversation_job_records_task_id(fake_delay) -> None:
    conversation = Conversation.objects.create(initial_prompt="hello", session_id="session-5")
    message = Message.objects.create(conversation=conversation, role=MessageRole.USER, text="hello")

    job = enqueue_conversation_job(conversation, request_message=message)

    assert job.celery_task_id.startswith("task-")
    assert Event.objects.filter(conversation=conversation, kind="job_enqueued").exists()


@pytest.mark.parametrize(
    ("result", "expected_status"),
    [
        (WorkflowResult(status="completed", response="ok"), "completed"),
        (WorkflowResult(status="failed", error="boom"), "failed"),
        (WorkflowResult(status="paused_for_approval"), "paused_for_approval"),
    ],
)
def test_celery_task_reports_serializable_result(
    monkeypatch,
    result: WorkflowResult,
    expected_status: str,
) -> None:
    monkeypatch.setattr("apps.api.conversations.tasks.run_job", lambda job_id: result)

    payload = run_conversation_job.run(17)

    assert payload["job_id"] == 17
    assert payload["status"] == expected_status


@pytest.mark.django_db
def test_create_conversation_api_returns_json(client, fake_delay) -> None:
    response = client.post(
        "/conversations",
        data=json.dumps({"prompt": "inspect current playbooks"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["initial_prompt"] == "inspect current playbooks"
    assert payload["messages"][0]["text"] == "inspect current playbooks"
    assert Conversation.objects.get(id=payload["id"]).jobs.count() == 1


@pytest.mark.django_db
def test_conversation_endpoints_return_history(client) -> None:
    conversation = Conversation.objects.create(initial_prompt="hello", session_id="session-6")
    message = Message.objects.create(conversation=conversation, role=MessageRole.USER, text="hello")
    job = Job.objects.create(
        conversation=conversation,
        request_message=message,
        submitted_payload={"prompt": "hello"},
    )
    Event.objects.create(
        conversation=conversation,
        job=job,
        kind="status",
        status="running",
        message="Running",
    )

    detail_response = client.get(f"/conversations/{conversation.id}")
    messages_response = client.get(f"/conversations/{conversation.id}/messages")
    events_response = client.get(f"/conversations/{conversation.id}/events")
    jobs_response = client.get(f"/conversations/{conversation.id}/jobs")

    assert detail_response.status_code == 200
    assert messages_response.json()["messages"][0]["id"] == message.id
    assert events_response.json()["events"][0]["kind"] == "status"
    assert jobs_response.json()["jobs"][0]["id"] == job.id


@pytest.mark.django_db
def test_create_conversation_message_enqueues_job(fake_delay) -> None:
    conversation = Conversation.objects.create(
        initial_prompt="hello",
        session_id="session-7",
        status=ConversationStatus.COMPLETED,
    )

    message = submit_conversation_message(conversation, text="follow up")

    conversation.refresh_from_db()
    assert conversation.status == ConversationStatus.QUEUED
    assert message.role == MessageRole.USER
    assert conversation.jobs.count() == 1


@pytest.mark.django_db
def test_conversation_message_api_returns_json(client, fake_delay) -> None:
    conversation = Conversation.objects.create(
        initial_prompt="hello",
        session_id="session-8",
        status=ConversationStatus.COMPLETED,
    )

    response = client.post(
        f"/conversations/{conversation.id}/messages",
        data=json.dumps({"text": "follow up"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["text"] == "follow up"


@pytest.mark.django_db
def test_management_command_submits_conversation(fake_delay) -> None:
    stdout = StringIO()

    call_command("runconversation", "inspect loaded env vars", stdout=stdout)

    payload = json.loads(stdout.getvalue().strip())
    conversation = Conversation.objects.get(id=payload["id"])
    assert conversation.initial_prompt == "inspect loaded env vars"
    assert conversation.jobs.count() == 1
