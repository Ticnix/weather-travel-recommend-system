# 0001 · 逐小时天气以和风为主源，Open-Meteo 兜底

日期：2026-09-29 ｜ 状态：已采纳

## 背景

逐小时数据只有 Open-Meteo 提供（和风免费订阅未接逐小时），但部署环境实测：
容器到 Open-Meteo（境外 188.40.x.x）的 **TLS 会被间歇性掐断**
（DNS 正常、纯 HTTP 正常、仅 TLS EOF），主机侧却正常——境外直连在此网络不可靠。

## 决策

`fetch_hourly()` 以**和风 `/weather/24h`**（免费开发订阅即含、国内 CDN 直连稳定）
为主源；和风失败或未配 Key 时回退 Open-Meteo。两条源在
`weather_service.fetch_hourly` 归一化为统一的 `HourlyPoint`。

## 伴随约束

- 打分（`score_day`）必须用 `fetch_weather().daily`（DailyForecast），
  **不能用 `weather_sync.list_forecast` 的表行**——`WeatherHistory` 没有
  `temp_max/temp_min/date` 字段，会把每天都判成"数据不全"（实测踩过）。
- 跨客户端取不确定字段用 `getattr(..., None)`：两个客户端的
  `WeatherBundle` 形状不完全一致（和风路径无 `hourly` 字段）。

## 后果

- 国内/境外部署都能工作（两源互为地理冗余）；
- 逐小时有两条独立故障域，可用性高于任一单源；
- 代价：归一化代码多 ~30 行。
