import { expect, test } from '@playwright/test'
import { prepareLoggedIn } from './helpers'

/**
 * AI 一键排行程 E2E（Day 40）。
 *
 * **刻意不真跑生成**：那要调大模型，既慢又要钱，而且模型输出不稳定——
 * 拿它做断言等于自找 flaky。生成结果的正确性由
 * tests/unit/test_itinerary_planner.py（纯函数）与
 * src/components/TripPlanner.test.tsx（交互与映射）负责。
 *
 * 这里只验证「入口通、登录门槛对」——这两件事 E2E 才测得到。
 */
test.describe('AI 一键排行程', () => {
  test('未登录时可打开页签，但生成按钮不可用', async ({ page }) => {
    await page.goto('/recommend?tab=plan')

    await expect(page.getByText('AI 一键排行程')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByPlaceholder(/例如：周末想去广州玩两天/)).toBeVisible()
    // 未登录不该让用户白填一通再报 401
    await expect(page.getByRole('button', { name: /生成行程/ })).toBeDisabled()
    await expect(page.getByText(/登录后才能生成与保存/)).toBeVisible()
  })

  test('点示例标签会填入需求', async ({ page }) => {
    await page.goto('/recommend?tab=plan')
    await expect(page.getByText('AI 一键排行程')).toBeVisible({ timeout: 20_000 })

    await page.getByTestId('plan-example').first().click()

    await expect(page.getByPlaceholder(/例如：周末想去广州玩两天/)).toHaveValue(/广州/)
  })

  test('登录后生成按钮可用', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_plan')
    await page.goto('/recommend?tab=plan')

    await expect(page.getByRole('button', { name: /生成行程/ })).toBeEnabled({ timeout: 20_000 })
  })

  test('非法页签参数回落默认页签而不是白屏', async ({ page }) => {
    await page.goto('/recommend?tab=nonsense')

    // URL 参数被手改时不该渲染空白
    await expect(page.getByText('出行方案')).toBeVisible({ timeout: 20_000 })
  })
})
