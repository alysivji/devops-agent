from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from devops_bot.approval import ApprovalRequest, WaitingForApproval
from devops_bot.workflow import AgentWorkflow, WorkflowEvent, WorkflowResult

from .models import (
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

ACTIVE_CONVERSATION_STATUSES = {
    ConversationStatus.QUEUED,
    ConversationStatus.RUNNING,
    ConversationStatus.WAITING_FOR_APPROVAL,
}


class ActiveConversationExistsError(Exception):
    def __init__(self, conversation: Conversation) -> None:
        super().__init__(f"Conversation {conversation.id} is already active")
        self.conversation = conversation


class ConversationRunner(Protocol):
    def run(
        self,
        prompt: str,
        *,
        event_sink: Callable[[WorkflowEvent], None],
        approval_resolver: Callable[[ApprovalRequest], bool],
    ) -> WorkflowResult: ...


class ConversationRunnerFactory(Protocol):
    def __call__(self, *, session_id: str | None = None) -> ConversationRunner: ...


def create_conversation(*, prompt: str, session_id: str | None = None) -> Conversation:
    with transaction.atomic():
        active_conversation = (
            Conversation.objects.filter(status__in=ACTIVE_CONVERSATION_STATUSES)
            .order_by("created_at")
            .first()
        )
        if active_conversation is not None:
            raise ActiveConversationExistsError(active_conversation)

        conversation = Conversation.objects.create(
            initial_prompt=prompt,
            session_id=session_id or uuid4().hex,
        )
        user_message = Message.objects.create(
            conversation=conversation,
            role=MessageRole.USER,
            text=prompt,
        )
        Event.objects.create(
            conversation=conversation,
            kind="conversation_created",
            status=ConversationStatus.QUEUED,
            message="Conversation created.",
            details={"prompt": prompt},
        )
        enqueue_conversation_job(conversation, request_message=user_message)
        return conversation


def enqueue_conversation_job(
    conversation: Conversation,
    *,
    request_message: Message | None = None,
    kind: str = "prompt",
    submitted_payload: dict[str, object] | None = None,
) -> Job:
    from .tasks import run_conversation_job

    job = Job.objects.create(
        conversation=conversation,
        request_message=request_message,
        kind=kind,
        submitted_payload=submitted_payload
        or {"prompt": request_message.text if request_message else ""},
    )
    async_result = run_conversation_job.delay(job.id)
    job.celery_task_id = async_result.id
    job.save(update_fields=["celery_task_id", "updated_at"])
    Event.objects.create(
        conversation=conversation,
        job=job,
        kind="job_enqueued",
        status=JobStatus.QUEUED,
        message="Conversation job enqueued.",
        details={"task_id": async_result.id, "kind": kind},
    )
    return job


def submit_conversation(*, prompt: str, session_id: str | None = None) -> Conversation:
    return create_conversation(prompt=prompt, session_id=session_id)


def submit_conversation_message(
    conversation: Conversation,
    *,
    text: str,
) -> Message:
    with transaction.atomic():
        conversation.refresh_from_db()
        if conversation.status in ACTIVE_CONVERSATION_STATUSES:
            raise ValidationError("Conversation is already active.")

        conversation.status = ConversationStatus.QUEUED
        conversation.save(update_fields=["status", "updated_at"])
        message = Message.objects.create(
            conversation=conversation,
            role=MessageRole.USER,
            text=text,
        )
        enqueue_conversation_job(conversation, request_message=message)
        return message


def wait_for_conversation_completion(
    conversation: Conversation,
    *,
    poll_interval: float = 0.5,
    timeout_seconds: float = 30.0,
) -> Conversation:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        conversation.refresh_from_db()
        if conversation.status not in ACTIVE_CONVERSATION_STATUSES:
            return conversation
        time.sleep(poll_interval)

    raise TimeoutError(f"Timed out waiting for conversation {conversation.id}")


def run_job(
    job_id: int,
    *,
    agent_factory: ConversationRunnerFactory = AgentWorkflow,
) -> WorkflowResult:
    with transaction.atomic():
        job = Job.objects.select_related("conversation", "request_message").get(id=job_id)
        conversation = job.conversation
        job.status = JobStatus.RUNNING
        conversation.status = ConversationStatus.RUNNING
        job.save(update_fields=["status", "updated_at"])
        conversation.save(update_fields=["status", "updated_at"])

    pending_approval = _load_resumable_approval(job)
    conversation_runner = agent_factory(session_id=conversation.session_id)
    prompt = str(
        job.submitted_payload.get("prompt")
        or (
            job.request_message.text
            if job.request_message is not None
            else conversation.initial_prompt
        )
    )
    result = conversation_runner.run(
        prompt,
        event_sink=lambda event: _record_runtime_event(
            conversation=conversation,
            job=job,
            event=event,
        ),
        approval_resolver=lambda request: _resolve_approval(
            conversation=conversation,
            job=job,
            request=request,
            approved_request=pending_approval,
        ),
    )
    _apply_result(conversation=conversation, job=job, result=result)
    return result


def approve_pending_approval(pending_approval: PendingApproval) -> Job:
    if pending_approval.status != ApprovalStatus.PENDING:
        raise ValidationError("Approval is no longer pending.")

    with transaction.atomic():
        pending_approval.status = ApprovalStatus.APPROVED
        pending_approval.save(update_fields=["status", "updated_at"])
        conversation = pending_approval.conversation
        conversation.status = ConversationStatus.QUEUED
        conversation.save(update_fields=["status", "updated_at"])

        Event.objects.create(
            conversation=conversation,
            job=pending_approval.job,
            kind="approval_approved",
            status=ApprovalStatus.APPROVED,
            message="Approval approved.",
            details={"pending_approval_id": pending_approval.id},
        )
        return enqueue_conversation_job(
            conversation,
            kind="approval_resume",
            submitted_payload={
                "prompt": pending_approval.prompt,
                "pending_approval_id": pending_approval.id,
            },
        )


def decline_pending_approval(pending_approval: PendingApproval) -> PendingApproval:
    if pending_approval.status != ApprovalStatus.PENDING:
        raise ValidationError("Approval is no longer pending.")

    with transaction.atomic():
        pending_approval.status = ApprovalStatus.DECLINED
        pending_approval.save(update_fields=["status", "updated_at"])
        conversation = pending_approval.conversation
        conversation.status = ConversationStatus.FAILED
        conversation.error_text = "Approval declined."
        conversation.save(update_fields=["status", "error_text", "updated_at"])
        if pending_approval.job is not None:
            pending_approval.job.status = JobStatus.FAILED
            pending_approval.job.error_text = "Approval declined."
            pending_approval.job.save(update_fields=["status", "error_text", "updated_at"])

        Event.objects.create(
            conversation=conversation,
            job=pending_approval.job,
            kind="approval_declined",
            status=ApprovalStatus.DECLINED,
            message="Approval declined.",
            details={"pending_approval_id": pending_approval.id},
        )
        return pending_approval


def serialize_conversation(conversation: Conversation) -> dict[str, object]:
    return {
        "id": conversation.id,
        "initial_prompt": conversation.initial_prompt,
        "status": conversation.status,
        "session_id": conversation.session_id,
        "final_summary": conversation.final_summary,
        "error_text": conversation.error_text,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


def serialize_job(job: Job) -> dict[str, object]:
    return {
        "id": job.id,
        "conversation_id": job.conversation_id,
        "request_message_id": job.request_message_id,
        "kind": job.kind,
        "celery_task_id": job.celery_task_id,
        "status": job.status,
        "submitted_payload": job.submitted_payload,
        "result_text": job.result_text,
        "error_text": job.error_text,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def serialize_event(event: Event) -> dict[str, object]:
    return {
        "id": event.id,
        "conversation_id": event.conversation_id,
        "job_id": event.job_id,
        "kind": event.kind,
        "status": event.status,
        "message": event.message,
        "details": event.details,
        "created_at": event.created_at.isoformat(),
    }


def serialize_pending_approval(pending_approval: PendingApproval) -> dict[str, object]:
    return {
        "id": pending_approval.id,
        "conversation_id": pending_approval.conversation_id,
        "job_id": pending_approval.job_id,
        "kind": pending_approval.kind,
        "prompt": pending_approval.prompt,
        "action_payload": pending_approval.action_payload,
        "status": pending_approval.status,
        "created_at": pending_approval.created_at.isoformat(),
        "updated_at": pending_approval.updated_at.isoformat(),
    }


def serialize_message(message: Message) -> dict[str, object]:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "text": message.text,
        "created_at": message.created_at.isoformat(),
    }


def _apply_result(*, conversation: Conversation, job: Job, result: WorkflowResult) -> None:
    with transaction.atomic():
        conversation.refresh_from_db()
        job.refresh_from_db()

        if result.status == "completed":
            conversation.status = ConversationStatus.COMPLETED
            conversation.final_summary = result.response or ""
            conversation.error_text = ""
            job.status = JobStatus.COMPLETED
            job.result_text = result.response or ""
            job.error_text = ""
            if result.response:
                Message.objects.create(
                    conversation=conversation,
                    role=MessageRole.ASSISTANT,
                    text=result.response,
                )
        elif result.status == "paused_for_approval":
            conversation.status = ConversationStatus.WAITING_FOR_APPROVAL
            job.status = JobStatus.WAITING_FOR_APPROVAL
        else:
            conversation.status = ConversationStatus.FAILED
            conversation.error_text = result.error or "Unknown conversation failure."
            job.status = JobStatus.FAILED
            job.error_text = result.error or "Unknown conversation failure."
            if result.error:
                Message.objects.create(
                    conversation=conversation,
                    role=MessageRole.ERROR,
                    text=result.error,
                )

        conversation.save(update_fields=["status", "final_summary", "error_text", "updated_at"])
        job.save(update_fields=["status", "result_text", "error_text", "updated_at"])


def _record_runtime_event(*, conversation: Conversation, job: Job, event: WorkflowEvent) -> None:
    message = str(
        event.get("text") or event.get("prompt") or event.get("title") or event.get("body") or ""
    )
    Event.objects.create(
        conversation=conversation,
        job=job,
        kind=event["kind"],
        status=_event_status(event),
        message=message,
        details=dict(event),
    )


def _event_status(event: WorkflowEvent) -> str:
    if event["kind"] == "approval_resolved":
        return "approved" if event.get("approved") else "declined"
    if event["kind"] == "notice":
        return str(event.get("level", "info"))
    if event["kind"] == "message":
        return str(event.get("role", "agent"))
    if event["kind"] in {"run_started", "status"}:
        return "running"
    if event["kind"] == "run_completed":
        return "completed"
    if event["kind"] == "run_failed":
        return "failed"
    if event["kind"] == "approval_requested":
        return "pending"
    return ""


def _resolve_approval(
    *,
    conversation: Conversation,
    job: Job,
    request: ApprovalRequest,
    approved_request: PendingApproval | None,
) -> bool:
    if approved_request is not None and _approval_matches(approved_request, request):
        return True

    PendingApproval.objects.create(
        conversation=conversation,
        job=job,
        kind=request["kind"],
        prompt=request["prompt"],
        action_payload=request["context"],
    )
    raise WaitingForApproval(request=request)


def _approval_matches(pending_approval: PendingApproval, request: ApprovalRequest) -> bool:
    return (
        pending_approval.status == ApprovalStatus.APPROVED
        and pending_approval.kind == request["kind"]
        and pending_approval.prompt == request["prompt"]
        and pending_approval.action_payload == request["context"]
    )


def _load_resumable_approval(job: Job) -> PendingApproval | None:
    pending_approval_id = job.submitted_payload.get("pending_approval_id")
    if not isinstance(pending_approval_id, int):
        return None
    return PendingApproval.objects.filter(id=pending_approval_id).first()
