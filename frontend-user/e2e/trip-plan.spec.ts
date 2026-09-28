import { expect, test } from '@playwright/test'
import { prepareLoggedIn } from './helpers'

/** 生成接口的桩数据：只为让"等待中"这一屏稳定停留，不校验生成内容 */
const PLAN_STUB = {
  code: 0,
  message: 'ok',
  data: {
    request: {
      city: '广州',
      days: 1,
      preferences: [],
      city_assumed: false,
      start_date: null,
      date_hint: null,
      area: null,
      area_hint: null,
    },
    dates: ['2026-09-19'],
    weather: {},
    weather_hint: null,
    area_note: null,
    plan: {
      city: '广州',
      days: 1,
      summary: '桩数据',
      plan: [
        {
          date: '2026-09-19',
          weather: '',
          weather_note: '',
          items: [
            {
              time: '09:30',
              title: '广东省博物馆',
              activity: '看展',
              reason: '桩数据',
              weather_adjusted: false,
            },
          ],
        },
      ],
    },
    adjustments: [],
  },
}

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

  test('生成期间同时给出文字说明与加载图标，而不是只留骨架屏', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_plan_wait')
    // 把生成接口延迟 8 秒再返回：这一屏原本一闪而过，无法断言（也避免真跑大模型）
    await page.route('**/api/v1/recommend/plan', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 8000))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(PLAN_STUB),
      })
    })

    await page.goto('/recommend?tab=plan')
    await expect(page.getByText('AI 一键排行程')).toBeVisible({ timeout: 20_000 })
    await page.getByPlaceholder(/例如：周末想去广州玩两天/).fill('国庆去广州玩几天')
    await page.getByRole('button', { name: /生成行程/ }).click()

    const waiting = page.getByTestId('loading-state')
    await expect(waiting).toBeVisible()
    // 1. 要说清在做什么、要等多久（骨架屏做不到这件事）
    await expect(waiting).toContainText('正在为你生成行程')
    await expect(waiting).toContainText('10~30 秒')
    // 2. 加载图标要真的渲染出来，而不是一个空占位
    await expect(waiting.locator('img')).toBeVisible()
    await expect(waiting.locator('img')).toHaveAttribute('src', /loading.*\.gif/)
  })

  test('行程里的地点名可以点开地图看位置', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_plan_map')
    await page.route('**/api/v1/recommend/plan', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(PLAN_STUB),
      })
    })

    await page.goto('/recommend?tab=plan')
    await expect(page.getByText('AI 一键排行程')).toBeVisible({ timeout: 20_000 })
    await page.getByPlaceholder(/例如：周末想去广州玩两天/).fill('明天去广州玩')
    await page.getByRole('button', { name: /生成行程/ }).click()

    // 地点名要能点开地图：目标是高德，且在新窗口打开（不能把用户从行程页带走）
    const link = page.getByTestId('map-link').first()
    await expect(link).toBeVisible({ timeout: 20_000 })
    await expect(link).toHaveAttribute('href', /uri\.amap\.com/)
    await expect(link).toHaveAttribute('target', '_blank')
  })
})
