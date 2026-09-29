# Roadmap（未完成事项）

> 已完成部分见 [features.md](features.md)；逐日明细见 [../history/28天开发计划.md](../history/28天开发计划.md)。

## 高优先级

- [ ] **多城市订阅**：现在隐性支持（行程城市自动适配），缺显式的城市管理 UI 与逐城市推送
- [ ] **早报全文语音播报**：当前播报的是首页提醒；早报文本入口就绪后接入
- [ ] **best-days 前端入口**：`GET /recommend/best-days` 已上线（实测 6/7 天），缺行程页/AI 工具的展示位

## 中优先级

- [ ] Day 61 完整版：语音播报支持打断续播、语速/音色设置
- [ ] Day 62 一致性清理：Placeholder 组件、landmark 语义、admin 端同款收尾
- [ ] 空气质量历史趋势（Open-Meteo air-quality 也有历史 API，与温度趋势同页展示）

## 低优先级 / 想法

- [ ] 行程协作邀请（多人共享一份行程）
- [ ] 和风付费能力评估：官方预警（现在用阈值规则兜底）、AQI 官方源
- [ ] 逐小时曲线手势优化：捏合缩放时间窗

## 已知技术债

- [ ] `weather_client` 与 `qweather_client` 各自定义同名 dataclass（CurrentWeather 等），形状靠约定对齐——应上提到共享 schema
- [ ] `weather_sync.list_forecast` 返回表行（无 temp_max），与 `score_day` 期望的 DailyForecast 割裂，容易再踩（decisions/0001 有记录）
- [ ] 仓库历史中早期提交署名为 Administrator（重写需强推，已放弃；仅影响贡献者图）
