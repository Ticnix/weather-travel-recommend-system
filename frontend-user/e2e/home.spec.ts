import { expect, test } from '@playwright/test'

/**
 * 核心路径 ②：首页自动看到天气、提醒、穿搭、行程。
 *
 * 断言刻意写得「宽松」：只校验结构与关键元素是否出现，
 * **不校验具体温度/天气文案**——那些取决于实时天气，
 * 写死了会变成"天气一变测试就红"的假失败。
 */

test.describe('首页仪表盘（未登录）', () => {
  test('打开首页即自动展示实时天气', async ({ page }) => {
    await page.goto('/')

    // 天气主卡片：温度与体感来自 /weather/current。
    // 注意组件里写的是「°C」（度符号+C）而不是单字符「℃」
    await expect(page.getByText(/°C/).first()).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('体感')).toBeVisible()
    // 湿度 / 风速 / 降水 / 能见度 四个指标
    await expect(page.getByText('湿度')).toBeVisible()
    await expect(page.getByText('风速')).toBeVisible()
  })

  test('今日提醒与今日穿搭区块直接可见（无需跳转）', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByText('今日提醒')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('今日穿搭')).toBeVisible()
  })

  test('天气时间轴默认展示「今天 + 未来一周」', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByText('天气时间轴')).toBeVisible({ timeout: 20_000 })
    // 默认区间是「未来 7 天」，今天排最左
    await expect(page.getByText('未来 7 天')).toBeVisible()
    await expect(page.getByText('今天').first()).toBeVisible()
    // 区间图例
    await expect(page.getByText('未来 · 预报')).toBeVisible()
  })

  test('可切换到「近 30 天」并回到今天', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('天气时间轴')).toBeVisible({ timeout: 20_000 })

    // Segmented 的 radio input 视觉隐藏，要点可见的文本 label
    await page.getByText('近 30 天', { exact: true }).click()
    // 过去区间才有「实况」标记
    await expect(page.getByText('实况').first()).toBeVisible({ timeout: 15_000 })

    // 「回到今天」按钮不报错即可（滚动行为难以断言）
    await page.getByRole('button', { name: /回到今天/ }).click()
  })

  test('未登录时行程区块提示登录', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('近期行程')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByText('登录后可查看行程安排与天气提醒')).toBeVisible()
  })

  test('导航栏可跳转到各主要页面', async ({ page }) => {
    await page.goto('/')

    const routes: Array<[string, RegExp]> = [
      ['气象资讯', /\/news/],
      ['意见反馈', /\/feedback/],
      ['智能推荐', /\/recommend/],
    ]

    for (const [label, url] of routes) {
      // antd Menu 渲染为 menuitem role，比文本匹配更稳（页面内容里可能有同名文字）
      await page.getByRole('menuitem', { name: label }).click()
      await expect(page).toHaveURL(url)
      await page.goto('/')
    }
  })
})
