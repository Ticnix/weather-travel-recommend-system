"""CSV 数据清洗引擎（基于 Pandas）。

实现四类清洗规则：
1. 去重：按业务主键去重
2. 缺失填充：数值列用中位数、分类列用众数、时间列用前向填充
3. 异常过滤：基于 IQR 或合理范围阈值剔除离群点
4. 单位标准化：温度华氏→摄氏、风速 m/s→km/h、气压 kPa→hPa 等

清洗过程产生结构化日志，便于审计与回溯。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CleanStats:
    """清洗统计结果。"""

    total_rows: int = 0
    cleaned_rows: int = 0
    duplicated_removed: int = 0
    filled_missing: int = 0
    filtered_outliers: int = 0
    unit_standardized: int = 0  # 标准化的列数
    log_lines: list[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
        self.log_lines.append(line)
        logger.info(msg)

    @property
    def log_text(self) -> str:
        return "\n".join(self.log_lines)


# 列名别名映射：把常见异名统一为标准名
COLUMN_ALIASES: dict[str, str] = {
    "temp": "temperature",
    "temperature_c": "temperature",
    "temperature_f": "temperature",  # 华氏度，后续做单位转换
    "hum": "humidity",
    "rh": "humidity",
    "press": "pressure",
    "pressure_hpa": "pressure",
    "pressure_kpa": "pressure",  # kPa，后续转换
    "wind": "wind_speed",
    "speed": "wind_speed",
    "wind_ms": "wind_speed",  # m/s，后续转换
    "precip": "precipitation",
    "rain": "precipitation",
    "vis": "visibility",
    "location": "location_code",
    "city": "location_code",
    "time": "time",
    "datetime": "time",
    "date": "time",
}

# 数值列合理范围（用于异常过滤；超出视为离群点置 NaN 后填充）
NUMERIC_RANGES: dict[str, tuple[float, float]] = {
    "temperature": (-50, 60),  # ℃
    "feels_like": (-60, 70),
    "humidity": (0, 100),  # %
    "pressure": (800, 1100),  # hPa
    "wind_speed": (0, 200),  # km/h
    "precipitation": (0, 500),  # mm
    "visibility": (0, 100),  # km
}

# 单位标准化：列名后缀 → (目标列名, 原单位, 目标单位, 转换函数)
# 检测列名是否以这些后缀结尾，触发对应转换
UNIT_SUFFIX_RULES: list[tuple[str, str, str, str, object]] = [
    ("_f", "temperature", "℉", "℃", lambda x: (x - 32) * 5 / 9),
    ("_k", "temperature", "K", "℃", lambda x: x - 273.15),
    ("_kpa", "pressure", "kPa", "hPa", lambda x: x * 10),
    ("_ms", "wind_speed", "m/s", "km/h", lambda x: x * 3.6),
    ("_m", "visibility", "m", "km", lambda x: x / 1000),
]


def clean_csv(
    input_path: str | Path, output_path: str | Path, dedup_keys: list[str] | None = None
) -> CleanStats:
    """清洗单个 CSV 文件，输出清洗后 CSV，返回统计与日志。

    Args:
        input_path: 原始 CSV 路径
        output_path: 清洗后 CSV 输出路径
        dedup_keys: 去重依据的列名列表；默认按所有列去重
    """
    stats = CleanStats()
    input_path = Path(input_path)
    output_path = Path(output_path)

    # 1. 读取
    df = pd.read_csv(input_path, encoding="utf-8-sig")
    stats.total_rows = len(df)
    stats.log(f"读取原始文件 {input_path.name}：{stats.total_rows} 行，{len(df.columns)} 列")
    stats.log(f"原始列名：{list(df.columns)}")

    # 2. 列名清洗（仅去空格、小写，暂不做别名映射，避免与单位转换冲突）
    df.columns = [str(c).strip().lower() for c in df.columns]

    # 3. 单位标准化（基于列名后缀检测，必须在列名别名映射之前）
    standardized_cols = 0
    for col in list(df.columns):
        for suffix, target_col, orig_unit, target_unit, conv in UNIT_SUFFIX_RULES:
            if col.endswith(suffix):
                mask = pd.to_numeric(df[col], errors="coerce").notna()
                if mask.any():
                    df.loc[mask, target_col] = pd.to_numeric(
                        df.loc[mask, col], errors="coerce"
                    ).apply(conv)
                    df.loc[mask, target_col] = df.loc[mask, target_col].round(2)
                    standardized_cols += 1
                    stats.log(
                        f"单位标准化：{col}（{orig_unit}→{target_unit}）转换 {int(mask.sum())} 个值 → {target_col}"
                    )
                df = df.drop(columns=[col])
                break
    stats.unit_standardized = standardized_cols

    # 4. 列名别名映射（单位列已 drop，不会冲突）
    rename_map: dict[str, str] = {}
    for col in list(df.columns):
        if col in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[col]
    if rename_map:
        df = df.rename(columns=rename_map)
        stats.log(f"列名标准化：{rename_map}")

    # 4. 时间列解析
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        invalid_time = df["time"].isna().sum()
        if invalid_time:
            stats.log(f"时间列解析：{int(invalid_time)} 个无效时间置 NaT")
        df = df.dropna(subset=["time"])  # 时间无效的行直接丢弃
        stats.log(f"时间列解析完成，剩余 {len(df)} 行")

    # 5. 异常过滤：数值列超出合理范围 → 置 NaN（后续填充）
    outlier_total = 0
    for col, (lo, hi) in NUMERIC_RANGES.items():
        if col in df.columns:
            num = pd.to_numeric(df[col], errors="coerce")
            outliers = num.notna() & ((num < lo) | (num > hi))
            cnt = int(outliers.sum())
            if cnt:
                df.loc[outliers, col] = pd.NA
                outlier_total += cnt
                stats.log(f"异常过滤：{col} 超出 [{lo},{hi}] 的 {cnt} 个值置 NaN")
    stats.filtered_outliers = outlier_total

    # 6. 缺失填充
    filled_total = 0
    for col in df.columns:
        if col == "time":
            continue
        na_cnt = int(df[col].isna().sum())
        if na_cnt == 0:
            continue
        if col in NUMERIC_RANGES or pd.api.types.is_numeric_dtype(df[col]):
            med = pd.to_numeric(df[col], errors="coerce").median()
            if pd.isna(med):
                med = 0
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(med)
            stats.log(f"缺失填充：{col} 用中位数 {med:.2f} 填充 {na_cnt} 个")
        else:
            mode = df[col].mode(dropna=True)
            fill = mode[0] if len(mode) else "unknown"
            df[col] = df[col].fillna(fill)
            stats.log(f"缺失填充：{col} 用众数 '{fill}' 填充 {na_cnt} 个")
        filled_total += na_cnt
    stats.filled_missing = filled_total

    # 7. 去重
    before = len(df)
    keys = dedup_keys or list(df.columns)
    keys = [k for k in keys if k in df.columns]
    df = df.drop_duplicates(subset=keys or None, keep="first")
    stats.duplicated_removed = before - len(df)
    stats.log(f"去重：按 {keys or '全部列'} 删除 {stats.duplicated_removed} 行")

    # 8. 输出
    stats.cleaned_rows = len(df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    stats.log(f"清洗完成：输出 {stats.cleaned_rows} 行 → {output_path.name}")

    return stats
