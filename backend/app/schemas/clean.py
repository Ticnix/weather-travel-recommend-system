"""清洗模块 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CleanTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    filename: str
    status: str
    total_rows: int | None = None
    cleaned_rows: int | None = None
    duplicated_removed: int | None = None
    filled_missing: int | None = None
    filtered_outliers: int | None = None
    unit_standardized: int | None = None
    error: str | None = None
    triggered_by: str | None = None
    created_at: datetime
    updated_at: datetime


class CleanTaskDetail(CleanTaskOut):
    log: str | None = None
    stored_path: str | None = None


class UploadResult(BaseModel):
    task_id: str
    filename: str
    status: str
