import { expect, test, type Page } from '@playwright/test'

/**
 * 核心路径 ④：提交反馈。
 *
 * 反馈支持匿名提交，所以这条路径**不需要登录**——
 * 这也正是它值得单独覆盖的原因：未登录用户也能走通的链路。
 */

// 页面标题与导航栏菜单项同名（「意见反馈」），直接 getByText 会同时命中两个，
// 触发 strict mode violation；标题固定带 jp-serif 类，用它限定
const pageTitle = (page: Page) => page.locator('.jp-serif', { hasText: '意见反馈' })

test.describe('意见反馈', () => {
  test('未登录也能提交反馈并看到成功页', async ({ page }) => {
    await page.goto('/feedback')

    await expect(pageTitle(page)).toBeVisible({ timeout: 20_000 })
    await page
      .getByPlaceholder('请描述您遇到的问题或建议……')
      .fill(`E2E 自动化提交的反馈 ${Date.now()}`)
    await page.getByRole('button', { name: /提交反馈/ }).click()

    await expect(page.getByText('反馈提交成功')).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('button', { name: '查看我的反馈' })).toBeVisible()
  })

  test('未登录时提示匿名提交的限制', async ({ page }) => {
    await page.goto('/feedback')

    // 匿名提交无法关联账号，页面上有明确提示（避免用户提交完找不到回复）
    await expect(page.getByText('当前未登录，将以匿名方式提交')).toBeVisible({ timeout: 20_000 })
  })

  test('空内容不允许提交', async ({ page }) => {
    await page.goto('/feedback')
    await expect(pageTitle(page)).toBeVisible({ timeout: 20_000 })

    await page.getByRole('button', { name: /提交反馈/ }).click()

    await expect(page.getByText('请填写反馈内容')).toBeVisible()
  })

  test('可附加反馈类型标签', async ({ page }) => {
    await page.goto('/feedback')
    await expect(pageTitle(page)).toBeVisible({ timeout: 20_000 })

    await page.getByRole('button', { name: '功能建议' }).click()
    // 点击标签后内容框会自动补上【功能建议】前缀
    await expect(page.getByPlaceholder('请描述您遇到的问题或建议……')).toHaveValue(
      /【功能建议】/,
    )

    await page.getByPlaceholder('请描述您遇到的问题或建议……').fill(`【功能建议】E2E ${Date.now()}`)
    await page.getByRole('button', { name: /提交反馈/ }).click()
    await expect(page.getByText('反馈提交成功')).toBeVisible({ timeout: 20_000 })
  })
})
