from __future__ import annotations

from django.urls import path

from . import views

urlpatterns = [
    path("conversations", views.create_conversation_view, name="create-conversation"),
    path(
        "conversations/<int:conversation_id>",
        views.conversation_detail_view,
        name="conversation-detail",
    ),
    path(
        "conversations/<int:conversation_id>/messages",
        views.conversation_messages_view,
        name="conversation-messages",
    ),
    path(
        "conversations/<int:conversation_id>/events",
        views.conversation_events_view,
        name="conversation-events",
    ),
    path(
        "conversations/<int:conversation_id>/jobs",
        views.conversation_jobs_view,
        name="conversation-jobs",
    ),
    path(
        "pending-approvals/<int:pending_approval_id>/approve",
        views.approve_pending_approval_view,
        name="approve-pending-approval",
    ),
    path(
        "pending-approvals/<int:pending_approval_id>/decline",
        views.decline_pending_approval_view,
        name="decline-pending-approval",
    ),
]
