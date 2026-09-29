# 代码规范与已知陷阱

Lint 规则（ruff/eslint）负责格式；本文写的是**约定和踩过的坑**。

## 后端（FastAPI）

- **响应一律 `success(data, message=...)`** 包装 `{code, message, data}`；
  例外：文件下载（.ics 纯文本）直接返回 Response，套包装客户端读不懂。
- **鉴权**：路由参数 `current: CurrentUser`（必须登录）；
  可选登录用 OptionalUser 模式（`user_id = current.id if current else None`）。
- **service 层**：未传 `db` 时自建 `AsyncSession` 并提交——调用方按需传入。
- **业务错误**：service 抛 `ValueError`，router 转 `HTTPException(400)`；
  全局 `RequestValidationError` 处理器只取 `loc/msg`
  （pydantic v2 的 `errors()` 带原始异常对象，直接塞 JSON 会 500——已修，别退回）。
- **注释写"为什么"不写"是什么"**：来源是某次真实踩坑的，注明实测现象。
- **新表落盘三件套**：models/ 定义 + **注册进 models/__init__.py** +
  alembic 迁移（`create_all` 只建缺表不补列——改老表必须写迁移）。
- **创建新文件前先确认不存在**：write 工具会静默覆盖
  （recommend.py 曾被覆盖，智能推荐页全 404）。
- **恢复文件只用 `git checkout --`**：PowerShell `>` 重定向写出 UTF-16，
  Python 报 "null bytes"（recommend.py 二次事故）。

## 前端（React + antd v6）

- **`api/http.ts` 拦截器已解包 `{code, data}`**：api 模块拿到的 `res` 就是
  data 本体——再取 `res.data` 永远是 undefined（偏好刷新丢失的根因）。
- **改完前端先跑 `tsc -b` 再构建**：IDE lint 比 tsc 松
  （antd v6 `Popover` 没有 `styles.body` 这种差异只有 tsc 抓得住）；
  构建失败但容器还跑旧包，页面"没变化"极易误判。
- **跨客户端 dataclass 字段不一致**：取不确定存在的字段用 `getattr(x, k, None)`
  （weather_client 与 qweather_client 的 Bundle 形状不完全一致）。
- **上传前压缩图片**（长边 1600 + q0.85）：手机原图 8~15MB，超限要在
  **点选文件的那一刻**本地报错，别等上传 400。
- **移动端**：`useIsMobile()` 切换尺寸/文案；附件入口收进「+」号弹层，
  但**正在进行中的状态**（如录音）要直接露出按钮，不能藏进菜单。

## Git

- 仓库级身份已配置 `Ticnix <16281649+ticnix@users.noreply.github.com>`；
- 提交前 `git status` 扫一眼，临时脚本/截图不进仓库（.gitignore 已覆盖 `shot-*.png`、`.probe_*`）。
