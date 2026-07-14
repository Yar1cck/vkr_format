from celery import Celery

from services.core.vkr_core.config.settings import get_settings

settings = get_settings()

celery_client = Celery(
    "vkr_api_client",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


def enqueue_document_processing(document_id: str) -> None:
    celery_client.send_task("vkr.process_document", args=[document_id])
