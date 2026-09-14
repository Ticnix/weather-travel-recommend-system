import { defineConfig, devices } from '@playwright/test'

// 产物输出目录带时间戳：Playwright 启动时会清空 outputDir，而本机 IDE 劫持了
// Node 的递归删除（safe-delete shim），清理已存在的目录会直接报错；
// 用「每次全新、不存在的目录」则清理会被跳过，旧产物需要时手动删。
const runId =
  process.env.E2E_RUN_ID || new Date().toISOString().slice(0, 19).replace(/[:T-]/g, '')

/**
 * E2E 配置（Playwright）。
 *
 * 设计取向：**打真实运行的服务**，不 mock、不启 dev server。
 * E2E 的价值就在于「端到端真实」——前后端 + 数据库 + 外部依赖全都在链路上，
 * 单测覆盖不到的集成问题才会在这里暴露。
 *
 * 运行前请确保服务已启动：
 *   docker compose up -d
 *   npm run test:e2e
 *
 * 可用 E2E_BASE_URL 指向其他环境（如测试环境）。
 */
export default defineConfig({
  testDir: './e2e',

  // 用例会写真实数据（新增行程、提交反馈），串行执行避免互相干扰
  fullyParallel: false,
  workers: 1,

  // CI 上禁止 test.only（防止误提交只跑一个用例）
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,

  reporter: [['list'], ['html', { open: 'never' }]],

  // AI 对话要走 LLM，比较慢，统一放宽超时
  timeout: 90_000,
  expect: { timeout: 15_000 },

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:8080',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',

    // 失败留痕：截图 + 录像 + trace，三者配合基本能定位任何 UI 问题
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // 产物输出目录（截图/录像/trace 都在这里），runId 见文件顶部说明
  outputDir: `./e2e-results/${runId}`,
})
