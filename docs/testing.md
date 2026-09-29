# 测试

## 命令

| 层 | 命令 | 规模 |
| --- | --- | --- |
| 后端单元/集成 | `docker compose exec -T backend pytest -q` | 19 文件，覆盖率约 61% |
| 前端单元 | `cd frontend-user && npm test`（vitest） | NotificationSettings / TripPlanner / MapLink 等 |
| 前端类型 | `cd frontend-user && tsc -b` | **CI 与部署前必过** |
| Lint | `ruff check backend/app`、`npm run lint` | CI 有 ruff/eslint/pytest 全套 |

## 各层测什么

- **后端**：services 层为主（打分规则、判重逻辑、归一化、SSE 生成器）；
  路由层用 httpx AsyncClient + 测试库（conftest 用 create_all + 播种 `admin_t`）。
  **数据竞态的接口必须有并发测试**（曾抓到过 gather 结果错位的真 bug）。
- **前端 vitest**：交互逻辑（开关提交字段、邮箱校验），jsdom 里没有
  serviceWorker/PushManager，推送相关走"不支持"分支。
- **Playwright e2e**（`frontend-user/e2e/`）：关键用户流。
  ⚠️ PWA 的 Service Worker 会绕过 `page.route` 拦截，
  验证接口 mock 时必须 `serviceWorkers: 'block'`。

## 部署前回归清单（最小集）

1. `tsc -b` 通过；
2. 登录 → 首页（24h 曲线、AQI 徽标、今日提醒）；
3. 行程页：添加行程 → 风险徽标 → 导出 .ics（CRLF + VEVENT）→ 分享海报预览；
4. 聊天：只发附件能答、文字走 DeepSeek、图片走视觉；
5. 偏好保存 → 刷新后仍在（⚠️ 历史坑：响应解包层级）；
6. `GET /weather/hourly` 返回 24 点（主源和风）。

## 历史教训（为什么这么测）

- **静态检查全过 ≠ 能跑**：函数定义没落进文件、pydantic v2 的
  `errors()` 不可序列化、antd v6 的 `Popover.styles`——全是运行时才炸的。
- **必须真发一次请求**：前端 API 层多解包一层 `.data`，
  直连 HTTP 的 E2E 抓不到，只有页面级验证能暴露。
