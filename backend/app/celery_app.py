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
    include=[
        "app.tasks.weather_tasks",
        "app.tasks.clean_tasks",
        "app.tasks.rag_tasks",
        "app.tasks.news_tasks",
        "app.tasks.report_tasks",
    ],
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
        # 每天 7:30 / 17:30 采集气象资讯（中央气象台预警 + 本地天气简报）
        "collect-weather-news": {
            "task": "app.tasks.news_tasks.collect_weather_news",
            "schedule": crontab(hour="7,17", minute="30"),
        },
        # 每小时整点分发早报：按各用户设定的推送小时过滤（默认 7 点，
        # 用户可改到 5~10 点之间的任意整点，免打扰粒度为小时）
        "dispatch-morning-reports": {
            "task": "app.tasks.report_tasks.dispatch_morning_reports",
            "schedule": crontab(minute="0"),
        },
    },
)


# ---------------------------------------------------------------------------
# 任务失败全局告警（信号钩子：一处代码覆盖所有任务）
#
# 设计说明：告警走结构化日志而不是邮件——本机没有 SMTP 配置，
# 且日志已按 JSON 字段化，接告警平台时按 level=ERROR + logger=celery.alert 过滤即可。
# 邮件等通知渠道等真有值守需求时再作为扩展点接入。
# ---------------------------------------------------------------------------
import logging  # noqa: E402

from celery.signals import task_failure  # noqa: E402

alert_logger = logging.getLogger("celery.alert")


@task_failure.connect
def _alert_on_task_failure(
    sender=None,
    task_id: str | None = None,
    exception: BaseException | None = None,
    retries: int = 0,
    **_: object,
) -> None:
    """任务最终失败（重试耗尽）时的统一告警入口。"""
    alert_logger.error(
        "Celery 任务最终失败",
        extra={
            "task": getattr(sender, "name", str(sender)),
            "task_id": task_id,
            "retries": retries,
        },
        exc_info=exception,  # 异常实例（logging 3.5+ 支持），自动附上堆栈
    )
