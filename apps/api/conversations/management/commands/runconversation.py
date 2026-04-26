from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.api.conversations.services import (
    ActiveConversationExistsError,
    serialize_conversation,
    submit_conversation,
    wait_for_conversation_completion,
)


class Command(BaseCommand):
    help = "Create a conversation and enqueue the first Celery job."

    def add_arguments(self, parser) -> None:
        parser.add_argument("prompt")
        parser.add_argument("--session-id")
        parser.add_argument("--wait", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=0.5)
        parser.add_argument("--timeout", type=float, default=30.0)

    def handle(self, *args, **options) -> str:
        try:
            conversation = submit_conversation(
                prompt=options["prompt"],
                session_id=options["session_id"],
            )
        except ActiveConversationExistsError as exc:
            raise CommandError(
                "Conversation "
                f"{exc.conversation.id} is already active; wait for it to finish first."
            ) from exc

        if options["wait"]:
            conversation = wait_for_conversation_completion(
                conversation,
                poll_interval=options["poll_interval"],
                timeout_seconds=options["timeout"],
            )

        self.stdout.write(json.dumps(serialize_conversation(conversation)))
        return ""
