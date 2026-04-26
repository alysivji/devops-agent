from __future__ import annotations

from django.db import models


class ConversationStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_FOR_APPROVAL = "waiting_for_approval", "Waiting for approval"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class JobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_FOR_APPROVAL = "waiting_for_approval", "Waiting for approval"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    DECLINED = "declined", "Declined"


class Conversation(models.Model):
    initial_prompt = models.TextField()
    status = models.CharField(
        max_length=32,
        choices=ConversationStatus,
        default=ConversationStatus.QUEUED,
    )
    session_id = models.CharField(max_length=255, unique=True)
    final_summary = models.TextField(blank=True)
    error_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class MessageRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"
    SYSTEM = "system", "System"
    ERROR = "error", "Error"


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=32, choices=MessageRole)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class Job(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="jobs",
    )
    request_message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="jobs",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=64, default="prompt")
    celery_task_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, choices=JobStatus, default=JobStatus.QUEUED)
    submitted_payload = models.JSONField(default=dict)
    result_text = models.TextField(blank=True)
    error_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]


class Event(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="events",
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="events",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=64)
    status = models.CharField(max_length=64, blank=True)
    message = models.TextField(blank=True)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class PendingApproval(models.Model):
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="pending_approvals",
    )
    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="pending_approvals",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=64)
    prompt = models.TextField()
    action_payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        choices=ApprovalStatus,
        default=ApprovalStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
