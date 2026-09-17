"""timescale analytics

启用 TimescaleDB 的时序分析能力：连续聚合 + 压缩 + 保留策略。
在此之前 weather_history 只是"建成了超表"，仍按普通表用——
每次统计都在原始行上现算 GROUP BY，超表的价值只兑现了一半。

Revision ID: 0011_timescale_analytics
Revises: 0010_notification_categories
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from app.db.analytics import DAILY_AGGREGATE_SELECT

revision: str = "0011_timescale_analytics"
down_revision: Union[str, None] = "0010_notification_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 日聚合视图名（连续聚合与测试库里的普通视图共用此名）
DAILY_VIEW = "weather_daily"


def _has_timescaledb(conn) -> bool:
    """当前库是否装了 timescaledb。

    没有就直接跳过：迁移要能在「没装 TimescaleDB 的环境」下跑过去
    （别人的本地库、CI 的普通 Postgres），而不是整条迁移链卡住。
    跳过的代价只是拿不到预聚合，业务查询仍可走普通视图。
    """
    row = conn.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
    ).first()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()

    if not _has_timescaledb(conn):
        print(">>> 未安装 timescaledb，跳过时序分析对象（连续聚合/压缩/保留）")
        return

    # 1) 连续聚合：日粒度预聚合
    #    WITH NO DATA 先建空壳，随后 refresh 补齐——
    #    直接 WITH DATA 在数据多时要等很久，迁移会卡住
    conn.execute(
        text(
            f"CREATE MATERIALIZED VIEW IF NOT EXISTS {DAILY_VIEW} "
            f"WITH (timescaledb.continuous) AS {DAILY_AGGREGATE_SELECT} "
            f"WITH NO DATA"
        )
    )

    # 2) 自动刷新策略：每小时刷一次，回看 400 天
    #    end_offset 留 1 小时：太接近当前时刻的数据还在写入，刷新了也会立刻过期
    conn.execute(
        text(
            f"SELECT add_continuous_aggregate_policy('{DAILY_VIEW}', "
            "start_offset => INTERVAL '400 days', "
            "end_offset => INTERVAL '1 hour', "
            "schedule_interval => INTERVAL '1 hour', "
            "if_not_exists => TRUE)"
        )
    )

    # 3) 压缩：按城市分段、按时间倒序
    #    segmentby 选 location_code：查询几乎总带城市条件，
    #    分段后同一城市的行连续存放，压缩率与扫描效率都更好
    conn.execute(
        text(
            "ALTER TABLE weather_history SET ("
            "timescaledb.compress, "
            "timescaledb.compress_segmentby = 'location_code', "
            "timescaledb.compress_orderby = 'time DESC')"
        )
    )
    # 30 天前的 chunk 才压缩：近期数据还要频繁更新（upsert），压了反而费
    conn.execute(
        text("SELECT add_compression_policy('weather_history', INTERVAL '30 days', if_not_exists => TRUE)")
    )

    # 4) 保留策略：超表保留 2 年
    #    与压缩策略不冲突：压的是老数据的存储形式，删的是过老的数据
    conn.execute(
        text("SELECT add_retention_policy('weather_history', INTERVAL '730 days', if_not_exists => TRUE)")
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not _has_timescaledb(conn):
        return

    # 策略先于对象删除：留着策略指向已删对象，后台任务会持续报错
    conn.execute(text("SELECT remove_retention_policy('weather_history', if_exists => TRUE)"))
    conn.execute(text("SELECT remove_compression_policy('weather_history', if_exists => TRUE)"))

    # ⚠️ 关压缩之前必须先把已压缩的 chunk 解压：
    # 压缩任务一旦跑过（这里就跑了），直接
    # `SET (timescaledb.compress = false)` 会报
    # `cannot disable columnstore on hypertable with columnstore chunks`。
    # 这个坑是回滚时才暴露的——正常升级路径根本走不到这一段。
    #
    # 写法上用 `show_chunks()` 而不是"查出名字再传参"：
    # `decompress_chunk` 的第一个形参是 **regclass**，
    # 传字符串绑参（`:c`）会被 asyncpg 当成 unknown 类型，
    # 报 `relation "_hyper_1_3_chunk" does not exist`（实测）。
    # `show_chunks()` 直接产出 regclass，顺带把解压写成一条集合语句。
    conn.execute(text("SELECT decompress_chunk(c, true) FROM show_chunks('weather_history') AS c"))

    conn.execute(text("ALTER TABLE weather_history SET (timescaledb.compress = false)"))
    conn.execute(
        text(f"SELECT remove_continuous_aggregate_policy('{DAILY_VIEW}', if_exists => TRUE)")
    )
    conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS {DAILY_VIEW}"))
