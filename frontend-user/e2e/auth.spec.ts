import { expect, test } from '@playwright/test'
import { makeAccount, TEST_PASSWORD } from './helpers'

/**
 * 核心路径 ①：注册 → 登录 → 退出。
 *
 * 这条路径走**完整 UI**（不打桩、不注入 token），因为它本身就是被测对象：
 * 表单校验、接口联动、登录态写入、跳转、退出清态，任何一环坏了这里都会红。
 */

test.describe('注册 / 登录 / 退出', () => {
  test('新用户可注册并自动登录', async ({ page, request }) => {
    // 先确认服务在跑（health 在后端根路径，8080 代理不到，改用业务接口探活）
    await request.get('/api/v1/weather/current')
    const account = makeAccount('e2e_reg')

    await page.goto('/login')
    // 切到注册模式。
    // 注意：antd Segmented 的 radio input 是视觉隐藏的（opacity:0），
    // 点击它会因「不可见」而超时；要点的是可见的文本 label。
    await page.getByText('注册', { exact: true }).click()

    await page.getByPlaceholder('3-64 位字符').fill(account.username)
    await page.getByPlaceholder('至少 6 位').fill(account.password)
    await page.getByRole('button', { name: '注册并登录' }).click()

    // 注册成功会自动登录并跳转「我的」页
    await expect(page).toHaveURL(/\/profile/)
    await expect(page.getByText(`@${account.username}`)).toBeVisible()
  })

  test('密码错误时页面给出提示', async ({ page, request }) => {
    await request.get('/api/v1/weather/current')
    const account = makeAccount('e2e_badpwd')

    // 先注册一个真账号
    await request.post('/api/v1/users/register', {
      data: { username: account.username, password: account.password },
    })

    await page.goto('/login')
    await page.getByPlaceholder('3-64 位字符').fill(account.username)
    await page.getByPlaceholder('至少 6 位').fill('WrongPassword123')
    // antd 会把「登录」渲染成「登 录」（两字按钮自动插空格），用正则匹配
    await page.getByRole('button', { name: /登\s*录/ }).click()

    // 后端返回 401，登录页把错误信息展示出来（而不是静默失败）
    await expect(page.getByText('用户名或密码错误')).toBeVisible()
  })

  test('表单校验：用户名过短与密码过短都会被拦下', async ({ page }) => {
    await page.goto('/login')
    await page.getByText('注册', { exact: true }).click()

    await page.getByPlaceholder('3-64 位字符').fill('ab')
    await page.getByPlaceholder('至少 6 位').fill('123')
    await page.getByRole('button', { name: '注册并登录' }).click()

    await expect(page.getByText('用户名 3-64 个字符')).toBeVisible()
    await expect(page.getByText('密码至少 6 位')).toBeVisible()
  })

  test('登录后可退出，登录态被清除', async ({ page, request }) => {
    const account = makeAccount('e2e_logout')
    await request.post('/api/v1/users/register', {
      data: { username: account.username, password: account.password },
    })

    await page.goto('/login')
    await page.getByPlaceholder('3-64 位字符').fill(account.username)
    await page.getByPlaceholder('至少 6 位').fill(TEST_PASSWORD)
    // antd 两字按钮自动插空格（「登 录」），用正则匹配
    await page.getByRole('button', { name: /登\s*录/ }).click()
    await expect(page).toHaveURL(/\/profile/)

    // 头部用户名下拉 → 退出登录。
    // 不用 getByRole('banner')：antd v6 的 Header 不能保证是 <header> 语义标签
    await page.getByText(account.username).first().click()
    await page.getByText('退出登录').click()

    // 退出后头部应重新出现「登录」按钮，且本地 token 被清掉
    await expect(page.getByRole('button', { name: /登\s*录/ })).toBeVisible()
    const token = await page.evaluate(() => localStorage.getItem('wt_token'))
    expect(token).toBeNull()
  })
})
