import { expect, test, type Page } from '@playwright/test'
import { prepareLoggedIn } from './helpers'

/**
 * 通知设置 E2E（Day 39）。
 *
 * 只覆盖「设置能改、能持久化」这条链路——
 * 真正的推送送达需要浏览器授权与推送服务，不适合放进自动化。
 * 每个用例都用全新账号（注册即默认全开），不依赖其他用例留下的设置。
 */
const sectionTitle = (page: Page) => page.locator('.jp-serif', { hasText: '通知设置' })

test.describe('通知设置', () => {
  test('关掉某一类推送后刷新仍然生效', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_notify')
    await page.goto('/profile')
    await expect(sectionTitle(page)).toBeVisible({ timeout: 20_000 })

    const alertSwitch = page.getByRole('switch', { name: '天气预警' })
    await expect(alertSwitch).toBeChecked()

    await alertSwitch.click()
    await expect(alertSwitch).not.toBeChecked()

    // 刷新后仍是关闭状态——说明真的落库了，而不是只改了前端状态
    await page.reload()
    await expect(sectionTitle(page)).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('switch', { name: '天气预警' })).not.toBeChecked()
  })

  test('三类开关互不影响', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_notify_indep')
    await page.goto('/profile')
    await expect(sectionTitle(page)).toBeVisible({ timeout: 20_000 })

    await page.getByRole('switch', { name: '行程提醒' }).click()

    // 只改了行程，另两类必须保持开启（部分更新而非全量覆盖）
    await expect(page.getByRole('switch', { name: '行程提醒' })).not.toBeChecked()
    await expect(page.getByRole('switch', { name: '每日早报' })).toBeChecked()
    await expect(page.getByRole('switch', { name: '天气预警' })).toBeChecked()
  })

  test('早报关闭后不再显示推送时间', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_notify_morning')
    await page.goto('/profile')
    await expect(sectionTitle(page)).toBeVisible({ timeout: 20_000 })

    const morningSwitch = page.getByRole('switch', { name: '每日早报' })
    await expect(morningSwitch).toBeChecked()
    await expect(page.getByText('07:00')).toBeVisible()

    // 关闭状态下调推送时间没有意义，应随之隐藏
    await morningSwitch.click()
    await expect(page.getByText('07:00')).toBeHidden()
  })

  test('未订阅设备时给出提示', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_notify_devices')
    await page.goto('/profile')
    await expect(sectionTitle(page)).toBeVisible({ timeout: 20_000 })

    await expect(page.getByText('推送设备')).toBeVisible()
    // 自动化环境没有真实推送订阅，应展示空态提示而不是一片空白
    await expect(page.getByText('当前没有已订阅的设备')).toBeVisible()
  })
})
