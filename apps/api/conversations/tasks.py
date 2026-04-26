from __future__ import annotations

from celery import shared_task

from .services import run_job


@shared_task(bind=True)
def run_conversation_job(self, job_id: int) -> dict[str, object]:
    result = run_job(job_id)
    return {
        "job_id": job_id,
        "status": result.status,
        "response": result.response,
        "error": result.error,
    }
