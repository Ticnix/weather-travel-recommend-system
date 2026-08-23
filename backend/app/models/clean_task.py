"""清洗任务记录表。

记录每次 CSV 清洗任务的元信息与执行日志，便于管理端查询任务状态与清洗过程。
"""

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CleanTask(Base, TimestampMixin):
    """CSV 数据清洗任务记录。"""

    __tablename__ = "clean_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)  # Celery task id
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 原始文件名
    stored_path: Mapped[str] = mapped_column(String(512), nullable=False)  # 服务器存储路径
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending/running/success/failed
    total_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 原始行数
    cleaned_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 清洗后行数
    duplicated_removed: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 去重删除数
    filled_missing: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 填充缺失数
    filtered_outliers: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 异常过滤数
    unit_standardized: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 单位标准化列数
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 失败原因
    log: Mapped[str | None] = mapped_column(Text, nullable=True)  # 清洗过程日志（逐步追加）
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 触发用户

    def __repr__(self) -> str:
        return f"<CleanTask {self.task_id} {self.status}>"
