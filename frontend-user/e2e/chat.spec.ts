import { expect, test } from '@playwright/test'
import { prepareLoggedIn } from './helpers'

/**
 * 核心路径 ⑤：AI 对话。
 *
 * 这条路径会**真实调用 LLM**（走 LangGraph Agent + MCP 工具），
 * 因此超时给得比较宽。它也是最有价值的一条 E2E——
 * 单测永远覆盖不到「前端流式解析 + 后端 Agent + 大模型」这一整条链路。
 *
 * 顺带把两个已修缺陷做成回归保护：
 *   - AI 回复必须渲染成 Markdown（曾出现标记裸显）
 *   - 登录用户的对话必须落库、刷新后能在左侧历史里看到（曾因流式请求漏带 token 而全丢）
 */

test.describe('AI 助手', () => {
  test('提问后能收到以 Markdown 渲染的回复', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_chat')
    await page.goto('/chat')

    // 用建议问题按钮发起提问，避免依赖输入法与回车行为
    await page.getByRole('button', { name: '广州今天天气怎么样' }).click()

    // 用户消息已入列（按钮 + 气泡会出现多次，取最后一个）
    await expect(page.getByText('广州今天天气怎么样').last()).toBeVisible({ timeout: 20_000 })

    // 助手回复以 Markdown 渲染（.jp-chat-md 是渲染容器）
    await expect(page.locator('.jp-chat-md').first()).toBeVisible({ timeout: 80_000 })
  })

  test('空输入时「发送」不会产生消息', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_chat_empty')
    await page.goto('/chat')

    await expect(page.getByText('和 AI 助手聊聊天气、穿搭、出行吧')).toBeVisible({
      timeout: 20_000,
    })
    await page.getByRole('button', { name: '发送' }).click()

    // 仍停留在欢迎态
    await expect(page.getByText('和 AI 助手聊聊天气、穿搭、出行吧')).toBeVisible()
    await expect(page.locator('.jp-chat-md')).toHaveCount(0)
  })

  test('登录用户的对话会出现在左侧历史会话中', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_chathis')
    await page.goto('/chat')

    // 登录后左侧应出现历史侧栏
    await expect(page.getByRole('button', { name: /新对话/ })).toBeVisible({ timeout: 20_000 })

    const question = `E2E历史会话${Date.now()}`
    await page.getByPlaceholder('输入你的问题，如：明天去广州塔穿什么？').fill(question)
    await page.getByRole('button', { name: '发送' }).click()

    // 等 AI 回复完成（回复落库发生在流式结束后）
    await expect(page.locator('.jp-chat-md').first()).toBeVisible({ timeout: 80_000 })
    // 流式渲染完不等于已落库（流结束后才写库），稍等片刻再刷新
    await page.waitForTimeout(3000)

    // 刷新页面：会话仍在（验证已落库 + 历史列表能拉到）
    await page.reload()
    await expect(page.getByText(question).first()).toBeVisible({ timeout: 30_000 })
  })
})
