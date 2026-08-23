"""清洗模块 Schema。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CleanTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    filename: str
    status: str
    total_rows: Optional[int] = None
    cleaned_rows: Optional[int] = None
    duplicated_removed: Optional[int] = None
    filled_missing: Optional[int] = None
    filtered_outliers: Optional[int] = None
    unit_standardized: Optional[int] = None
    error: Optional[str] = None
    triggered_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CleanTaskDetail(CleanTaskOut):
    log: Optional[str] = None
    stored_path: Optional[str] = None


class UploadResult(BaseModel):
    task_id: str
    filename: str
    status: str
