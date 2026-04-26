from __future__ import annotations

import json

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from .models import Conversation, PendingApproval
from .services import (
    ActiveConversationExistsError,
    approve_pending_approval,
    decline_pending_approval,
    serialize_conversation,
    serialize_event,
    serialize_job,
    serialize_message,
    serialize_pending_approval,
    submit_conversation,
    submit_conversation_message,
)


def _json_body(request: HttpRequest) -> dict[str, object]:
    if not request.body:
        return {}
    payload = json.loads(request.body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError("JSON body must be an object.")
    return payload


@csrf_exempt
def create_conversation_view(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    try:
        payload = _json_body(request)
        prompt = payload.get("prompt")
        session_id = payload.get("session_id")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValidationError("`prompt` is required.")
        if session_id is not None and not isinstance(session_id, str):
            raise ValidationError("`session_id` must be a string when provided.")
        conversation = submit_conversation(prompt=prompt, session_id=session_id)
    except ActiveConversationExistsError as exc:
        return JsonResponse(
            {
                "detail": "Another conversation is already active.",
                "active_conversation": serialize_conversation(exc.conversation),
            },
            status=409,
        )
    except (ValidationError, json.JSONDecodeError) as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    data = serialize_conversation(conversation)
    data["messages"] = [serialize_message(message) for message in conversation.messages.all()]
    return JsonResponse(data, status=201)


def conversation_detail_view(request: HttpRequest, conversation_id: int) -> JsonResponse:
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    conversation = get_object_or_404(Conversation, id=conversation_id)
    pending_approvals = [
        serialize_pending_approval(approval)
        for approval in conversation.pending_approvals.filter(status="pending")
    ]
    data = serialize_conversation(conversation)
    data["pending_approvals"] = pending_approvals
    return JsonResponse(data)


def conversation_messages_view(request: HttpRequest, conversation_id: int) -> JsonResponse:
    conversation = get_object_or_404(Conversation, id=conversation_id)
    if request.method == "GET":
        return JsonResponse(
            {"messages": [serialize_message(message) for message in conversation.messages.all()]}
        )

    if request.method == "POST":
        try:
            payload = _json_body(request)
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValidationError("`text` is required.")
            message = submit_conversation_message(conversation, text=text)
        except ValidationError as exc:
            return JsonResponse({"detail": str(exc)}, status=400)

        return JsonResponse(serialize_message(message), status=201)

    return JsonResponse({"detail": "Method not allowed."}, status=405)


def conversation_events_view(request: HttpRequest, conversation_id: int) -> JsonResponse:
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    conversation = get_object_or_404(Conversation, id=conversation_id)
    return JsonResponse({"events": [serialize_event(event) for event in conversation.events.all()]})


def conversation_jobs_view(request: HttpRequest, conversation_id: int) -> JsonResponse:
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    conversation = get_object_or_404(Conversation, id=conversation_id)
    return JsonResponse({"jobs": [serialize_job(job) for job in conversation.jobs.all()]})


@csrf_exempt
def approve_pending_approval_view(request: HttpRequest, pending_approval_id: int) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    pending_approval = get_object_or_404(PendingApproval, id=pending_approval_id)
    try:
        job = approve_pending_approval(pending_approval)
    except ValidationError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse(
        {
            "job": serialize_job(job),
            "approval": serialize_pending_approval(pending_approval),
        }
    )


@csrf_exempt
def decline_pending_approval_view(request: HttpRequest, pending_approval_id: int) -> JsonResponse:
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    pending_approval = get_object_or_404(PendingApproval, id=pending_approval_id)
    try:
        decline_pending_approval(pending_approval)
    except ValidationError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    pending_approval.refresh_from_db()
    return JsonResponse({"approval": serialize_pending_approval(pending_approval)})
