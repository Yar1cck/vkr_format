from celery import Celery
from celery.schedules import crontab

from services.core.vkr_core.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "vkr_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Moscow",
    enable_utc=False,
    # Подтверждаем задание только после завершения.
    # При падении/рестарте воркера задание вернётся в очередь.
    task_acks_late=True,
    # Не переподтверждать задание при восстановлении воркера.
    task_reject_on_worker_lost=True,
    # Жёсткие лимиты на задачу. Типичная обработка занимает 30-60с,
    # на больших документах с LibreOffice-конвертацией — до ~3 минут.
    # 5 минут — крайний срок: дальше почти всегда зависший soffice
    # или сломанный pipeline. Soft-limit (4 минуты) даёт задаче шанс
    # gracefully завершиться через SoftTimeLimitExceeded и пометить
    # документ как error в БД.
    task_soft_time_limit=240,
    task_time_limit=300,
    # Перезапускаем воркер после 50 задач — защита от накопления
    # утечек памяти (например, в процессе LibreOffice или PIL).
    worker_max_tasks_per_child=50,
    # Beat-расписание: ежесуточная очистка просроченных документов в 03:00
    # (Europe/Moscow — нагрузка минимальна). Beat-процесс запускается отдельным
    # сервисом `worker_beat` в docker-compose. Если запустить несколько beat'ов,
    # планировщик будет запускать задачу дважды — поэтому в проде должен быть
    # ровно один beat-процесс.
    beat_schedule={
        "vkr.cleanup-expired-daily": {
            "task": "vkr.cleanup_expired_documents",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)

celery_app.autodiscover_tasks(["services.worker.app"])
