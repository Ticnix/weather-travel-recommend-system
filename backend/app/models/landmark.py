from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Landmark(Base, TimestampMixin):
    """3D 地标表（PostGIS 几何字段存储经纬度点）。"""

    __tablename__ = "landmarks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # PostGIS 地理点（EPSG:4326 经纬度）
    location: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    altitude: Mapped[float | None] = mapped_column(nullable=True)  # 海拔/相对高度 m
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 景点/地标/场馆...
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 3D 模型地址
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<Landmark id={self.id} name={self.name}>"
