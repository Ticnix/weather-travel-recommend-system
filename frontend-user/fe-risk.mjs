/**
 * 验证 Day 52 前端：行程页风险徽标 + 通知设置新开关（临时脚本，用完即删）。
 *
 * 真实预报窗口没有强对流，扫不出命中，所以**拦截接口注入一条风险**来验证渲染。
 * 关键点：本应用带 Service Worker（PWA），SW 会**绕过 page.route**，
 * 必须 `serviceWorkers: 'block'` 才能拦到接口——第一次没屏蔽，结果就是"徽标不见了"。
 */
import { chromium } from 'playwright'

const BASE = process.env.VERIFY_BASE || 'http://localhost:8080'
const browser = await chromium.launch()
const ctx = await browser.newContext({
  viewport: { width: 390, height: 900 },
  isMobile: true,
  hasTouch: true,
  serviceWorkers: 'block',
})
const page = await ctx.newPage()
const out = { routeHits: 0 }

const res = await page.request.post(`${BASE}/api/v1/users/login`, {
  data: { username: 'admin', password: 'Admin@123456' },
})
const body = await res.json()
await page.addInitScript(
  ([t, u]) => {
    localStorage.setItem('wt_token', t)
    localStorage.setItem('wt_user', JSON.stringify(u))
  },
  [body.data.access_token, body.data.user],
)

// 1) 先真实打开一次，拿到行程 id
await page.goto(`${BASE}/itinerary`, { waitUntil: 'domcontentloaded' })
await page.waitForSelector('[data-itinerary-id]', { timeout: 20000 })
const itemId = await page.locator('[data-itinerary-id]').first().getAttribute('data-itinerary-id')
const allIds = await page.locator('[data-itinerary-id]').evaluateAll((els) =>
  els.map((el) => el.getAttribute('data-itinerary-id')),
)
out.itemId = itemId
out.allItemIds = allIds

// 2) 拦截风险接口
await page.route('**/itinerary/risks*', async (route) => {
  out.routeHits += 1
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      code: 0,
      message: 'ok',
      data: {
        items: [],
        by_itinerary: {
          [String(itemId)]: {
            itinerary_id: Number(itemId),
            date: '2026-09-25',
            kind: 'rain',
            level: 'danger',
            reason: '雷阵雨（24~33℃）',
            title: '⚠️ 09-25 白云山 遇降水',
            body: '你 2026-09-25 09:00 安排了「白云山爬山」（白云山）：雷阵雨（24~33℃）。建议改到 09-27（多云 25~33℃），那天更适合这类安排。',
          },
        },
        total: 1,
      },
    }),
  })
})

await page.reload({ waitUntil: 'domcontentloaded' })
await page.waitForTimeout(3000)

const badges = await page.locator('.ant-tag').allInnerTexts()
out.tags = badges
out.hasRiskBadge = badges.some((t) => t.includes('天气冲突'))
out.reminderSuppressedWhenRisk = !badges.some((t) => t.includes('会提醒'))

try {
  await page.locator('.ant-tag', { hasText: '天气冲突' }).first().hover({ timeout: 6000 })
  await page.waitForTimeout(900)
  out.tooltipHasAdvice = (await page.locator('text=建议改到').count()) > 0
} catch {
  out.tooltipHasAdvice = '未找到徽标，跳过悬停'
}
await page.screenshot({ path: 'risk-badge-mobile.png' })

// 3) 通知设置页：新开关（用专门的 /notifications 页，Profile 里那段可能要展开）
await page.goto(`${BASE}/notifications`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(4000)
const settingsText = await page.evaluate(() => document.body.innerText)
out.settingsHasCategory = settingsText.includes('行程天气预警')
out.settingsDesc = settingsText.includes('提前 1~3 天发现行程与天气冲突')
out.settingsRows = settingsText.split('\n').filter((l) => l.includes('预警') || l.includes('早报'))
await page.screenshot({ path: 'risk-settings-mobile.png' })

console.log(JSON.stringify(out, null, 2))
await ctx.close()
await browser.close()
