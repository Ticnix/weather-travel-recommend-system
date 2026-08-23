"""Celery 应用配置。

- broker/backend：Redis（与主应用共用）
- 定时任务：每小时同步一次广州气象数据
- 启动 worker：`celery -A app.celery_app worker -l info -P solo`（Windows 用 solo 池）
- 启动 beat：`celery -A app.celery_app beat -l info`
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "weather_travel",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.weather_tasks"],
)

celery_app.conf.update(
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue="weather",
    # Windows 兼容：默认 prefork 池在 Win 上有问题，建议启动时加 -P solo
    worker_prefetch_multiplier=1,
    beat_schedule={
        # 每小时第 5 分钟执行（避开整点高峰）
        "sync-weather-hourly": {
            "task": "app.tasks.weather_tasks.sync_weather_hourly",
            "schedule": crontab(minute="5"),
        },
    },
)
