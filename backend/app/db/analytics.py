"""时序聚合的统一定义（Day 42）。

**为什么把这段 SQL 单独放一个模块**：同一个聚合要在三处出现——

1. 生产环境：连续聚合（continuous aggregate）的定义，迁移 0010 里创建
2. 测试环境：测试库不建超表也不建连续聚合，用一个**同名的普通视图**顶上
3. 离线核对：需要手跑一遍聚合来对账时

如果三处各写一份，迟早会出现"测试通过的逻辑和线上跑的不是同一个 SQL"。
所以聚合定义在这里写一次，三处引用同一常量。

**日切为什么用 Asia/Shanghai**：`time_bucket('1 day', time)` 默认按 UTC 切，
广州（东八区）的"今天"会比北京时间晚 8 小时才归日——
晚上 8 点之后的数据会被算进前一天。所以显式传时区。
"""

from __future__ import annotations

# 日粒度聚合：均值 + 极值 + 累计 + 样本数
#
# ⚠️ 这张表里其实混了**两种行**（Day 4 的设计），聚合必须分别对待：
#
# | 行类型 | 来源 | temperature | feels_like | humidity |
# | --- | --- | --- | --- | --- |
# | 实测行 | 接口 current | 当时的温度 | 体感 | 有值 |
# | 日统计行 | 接口 daily | **日最高** | **日最低** | 为空 |
#
# 直接用 `avg(temperature)` 会把日统计行当成"当天的一个温度观测"，
# 于是"日均温"实际算成了"日最高温的均值"——数字看着正常，语义是错的。
# 所以用 `raw ? 'daily'` 区分两类行：
#   - 日统计行：用 (最高 + 最低) / 2 近似日均
#   - 实测行：用观测值本身
# 极值同理：日统计行的最低温存在 feels_like 里。
#
# 降水用 sum（日累计）而不是 avg：问"那天下多少雨"时答案是总量；
# 同时保留 avg，因为旧的 /weather/stats 返回的是平均值，两者都留着
# 才能既满足新需求又不破坏既有前端。
#
# samples 记录当日样本数：某天只有 1 个样本时，"最高/最低"其实没有代表性，
# 前端据此可以弱化展示（诚实标注数据质量，而不是假装精确）。
DAILY_AGGREGATE_SELECT = """
SELECT
    time_bucket('1 day', time, 'Asia/Shanghai') AS day,
    location_code,
    avg(
        CASE WHEN raw ? 'daily' THEN (temperature + feels_like) / 2
             ELSE temperature END
    ) AS temp_avg,
    max(temperature) AS temp_max,
    min(
        CASE WHEN raw ? 'daily' THEN feels_like
             ELSE temperature END
    ) AS temp_min,
    sum(precipitation) AS precip_sum,
    avg(precipitation) AS precip_avg,
    avg(humidity)      AS humidity_avg,
    count(*)           AS samples
FROM weather_history
WHERE is_forecast = false
GROUP BY day, location_code
"""
