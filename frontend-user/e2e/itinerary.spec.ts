import { expect, test, type Page } from '@playwright/test'
import { clearItinerary, prepareLoggedIn } from './helpers'

// 页面标题「我的行程」与导航菜单项同名，getByText 会命中两个触发 strict violation，
// 标题固定带 jp-serif 类，用它限定
const pageTitle = (page: Page) => page.locator('.jp-serif', { hasText: '我的行程' })

// 行程现在是「日期分组卡 + 时间轴行」，一条行程不再是独立卡片，
// 所以按行上的 data-itinerary-id 定位（那个属性只有行有）
const itineraryRow = (page: Page, title: string) =>
  page.locator('[data-itinerary-id]').filter({ hasText: title })

/** 开始时间改成了 TimePicker：不是文本框填充，而是选中输入框后键入时间再回车确认 */
async function pickStartTime(page: Page, value: string) {
  const input = page.getByPlaceholder('选择开始时间')
  await input.click()
  await input.fill(value)
  await page.keyboard.press('Enter')
  await page.keyboard.press('Escape')
}

/**
 * 核心路径 ③：登录 → 新增行程 → 编辑 → 删除。
 *
 * 这条路径覆盖了「行程」的完整生命周期，也是后端多租户隔离最容易出问题的地方
 * （每个用例都用全新账号，天然验证了"只能看到自己的行程"）。
 */

test.describe('我的行程', () => {
  test('新增行程后出现在列表中', async ({ page, request }) => {
    const account = await prepareLoggedIn(page, request, 'e2e_itin')
    await page.goto('/itinerary')

    await expect(pageTitle(page)).toBeVisible({ timeout: 20_000 })
    await page.getByRole('button', { name: /添加行程/ }).click()

    const title = `E2E-白云山爬山-${Date.now()}`
    await page.getByPlaceholder('如：迪士尼一日游').fill(title)
    await page.getByPlaceholder('选择日期').fill('2026-09-25')
    await page.keyboard.press('Enter')
    await pickStartTime(page, '09:00')
    await page.getByPlaceholder('如：上海迪士尼（会据此查询当地天气）').fill('白云山')
    await page.getByPlaceholder('如：游玩 / 爬山 / 逛街').fill('爬山')

    await page.getByRole('button', { name: '保 存' }).click()

    // 列表里应出现这条行程
    await expect(page.getByText(title)).toBeVisible({ timeout: 15_000 })

    await clearItinerary(request, account)
  })

  test('可以编辑已有行程的标题', async ({ page, request }) => {
    const account = await prepareLoggedIn(page, request, 'e2e_edit')
    await page.goto('/itinerary')
    await expect(pageTitle(page)).toBeVisible({ timeout: 20_000 })

    const title = `E2E-待修改-${Date.now()}`
    await page.getByRole('button', { name: /添加行程/ }).click()
    await page.getByPlaceholder('如：迪士尼一日游').fill(title)
    await page.getByPlaceholder('选择日期').fill('2026-09-26')
    await page.keyboard.press('Enter')
    await page.getByRole('button', { name: '保 存' }).click()
    await expect(page.getByText(title)).toBeVisible({ timeout: 15_000 })

    // 点击该条行程的「编辑」按钮（同一行内的第一个按钮）
    await itineraryRow(page, title).getByRole('button').first().click()

    const newTitle = `${title}-已改`
    await page.getByPlaceholder('如：迪士尼一日游').fill(newTitle)
    await page.getByRole('button', { name: '保 存' }).click()

    await expect(page.getByText(newTitle)).toBeVisible({ timeout: 15_000 })

    await clearItinerary(request, account)
  })

  test('删除行程后列表恢复空态', async ({ page, request }) => {
    // 这条用例自己会把行程删掉，无需收尾清理，所以不接住返回的 account
    await prepareLoggedIn(page, request, 'e2e_del')
    await page.goto('/itinerary')
    await expect(pageTitle(page)).toBeVisible({ timeout: 20_000 })

    const title = `E2E-待删除-${Date.now()}`
    await page.getByRole('button', { name: /添加行程/ }).click()
    await page.getByPlaceholder('如：迪士尼一日游').fill(title)
    await page.getByPlaceholder('选择日期').fill('2026-09-27')
    await page.keyboard.press('Enter')
    await page.getByRole('button', { name: '保 存' }).click()
    await expect(page.getByText(title)).toBeVisible({ timeout: 15_000 })

    // 删除：同一行里最后一个按钮是删除，点击后需在 Popconfirm 里确认
    await itineraryRow(page, title).getByRole('button').last().click()
    await page.getByRole('button', { name: '确 定' }).click()

    await expect(page.getByText(title)).toBeHidden({ timeout: 15_000 })
    await expect(page.getByText('还没有行程')).toBeVisible()
  })

  test('表单校验：不填标题不能保存', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_itin_valid')
    await page.goto('/itinerary')
    await expect(pageTitle(page)).toBeVisible({ timeout: 20_000 })

    await page.getByRole('button', { name: /添加行程/ }).click()
    await page.getByRole('button', { name: '保 存' }).click()

    await expect(page.getByText('请输入行程标题')).toBeVisible()
    await expect(page.getByText('请选择日期')).toBeVisible()
  })

  test('切换「行程笔记」标签展示笔记面板', async ({ page, request }) => {
    await prepareLoggedIn(page, request, 'e2e_note')
    await page.goto('/itinerary')
    await expect(pageTitle(page)).toBeVisible({ timeout: 20_000 })

    await page.getByText('📝 行程笔记').click()
    // 笔记面板有自己的新建入口
    await expect(page.getByRole('button', { name: /新建笔记/ })).toBeVisible({ timeout: 15_000 })
  })
})
