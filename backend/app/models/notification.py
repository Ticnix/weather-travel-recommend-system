"""通知数据模型：推送订阅、发送记录、通知偏好。"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PushSubscription(Base, TimestampMixin):
    """浏览器推送订阅（Web Push）。

    每台设备一条记录：同一用户可能同时用手机和电脑订阅，
    endpoint 由推送服务（FCM/Mozilla autopush）生成，全局唯一。
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)  # 加密公钥
    auth: Mapped[str] = mapped_column(String(255), nullable=False)  # 认证密钥
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationLog(Base, TimestampMixin):
    """通知发送记录（所有通道，成功与失败都留痕——Day 34 检查清单要求可查询）。

    status: sent（成功）/ failed（失败）/ skipped（通道未配置等原因跳过）
    """

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # web_push / email
    # 通知类型（Day 39）：morning / alert / itinerary / system。
    # 存下来才能让「推送历史」告诉用户这条是什么类型的，
    # 也才能在用户问"为什么没收到预警"时查到"被哪条偏好拦下了"。
    category: Mapped[str] = mapped_column(String(16), default="system", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotificationPref(Base, TimestampMixin):
    """每个用户一条偏好记录（user_id 唯一）。

    免打扰设计：morning_hour 的粒度是「小时」——
    Celery beat 每小时整点分发一次，按各用户设定的 hour 过滤，
    避免为每个用户单独注册一个定时任务。
    """

    __tablename__ = "notification_prefs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    morning_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    morning_hour: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    # 类型开关（Day 39）：让用户能按类型关掉打扰，而不是只能"全开或全关"。
    # 默认全开——用户没表达过意愿时，默认值应该是有用的那一边。
    alert_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    itinerary_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
