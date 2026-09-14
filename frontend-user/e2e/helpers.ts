import { expect, type APIRequestContext, type Page } from '@playwright/test'

/**
 * E2E 公共辅助。
 *
 * 核心目标：**用例可重复执行**。
 * 做法是每次生成唯一用户名，用完即弃——不去猜测"上一条测试留下的数据还剩什么"，
 * 这是 E2E 最常见的 flaky 来源。
 */

export const API_BASE = '/api/v1'
export const TEST_PASSWORD = 'E2e@Test123456'

export interface TestAccount {
  username: string
  password: string
}

/** 生成唯一用户名（时间戳 + 随机数），保证可重复执行不会撞名 */
export function uniqueName(prefix: string): string {
  const stamp = Date.now().toString(36)
  const rand = Math.floor(Math.random() * 1000)
  return `${prefix}_${stamp}${rand}`
}

export function makeAccount(prefix: string): TestAccount {
  return { username: uniqueName(prefix), password: TEST_PASSWORD }
}

/** 直接调接口注册（比走 UI 快；已存在也视为可用） */
export async function apiRegister(request: APIRequestContext, account: TestAccount): Promise<void> {
  const resp = await request.post(`${API_BASE}/users/register`, {
    data: { username: account.username, password: account.password },
  })
  expect([201, 409], `注册 ${account.username} 失败：${resp.status()}`).toContain(resp.status())
}

/** 直接调接口登录，返回 access_token */
export async function apiLogin(request: APIRequestContext, account: TestAccount): Promise<string> {
  const resp = await request.post(`${API_BASE}/users/login`, {
    data: { username: account.username, password: account.password },
  })
  expect(resp.ok(), '登录接口应返回 200').toBeTruthy()
  const body = await resp.json()
  return body.data.access_token as string
}

/**
 * 把登录态写入 localStorage，等价于"用户已登录"。
 *
 * 用于那些"只关心登录之后的业务"的用例，省掉每次都走一遍登录 UI 的时间。
 * 登录流程本身由 auth.spec.ts 真实覆盖。
 */
export async function loginByToken(page: Page, account: TestAccount, token: string): Promise<void> {
  await page.addInitScript(
    (payload: { token: string; username: string }) => {
      localStorage.setItem('wt_token', payload.token)
      localStorage.setItem(
        'wt_user',
        JSON.stringify({ username: payload.username, nickname: payload.username }),
      )
    },
    { token, username: account.username },
  )
}

/** 走完整 UI 登录流程 */
export async function uiLogin(page: Page, account: TestAccount): Promise<void> {
  await page.goto('/login')
  await page.getByPlaceholder('3-64 位字符').fill(account.username)
  await page.getByPlaceholder('至少 6 位').fill(account.password)
  // 注意：antd 会给两个字的按钮自动插空格（「登录」→「登 录」），
  // 精确文本匹配不到，用正则兼容空格
  await page.getByRole('button', { name: /登\s*录/ }).click()
}

/** 注册账号 + 注入登录态，返回账号信息 */
export async function prepareLoggedIn(
  page: Page,
  request: APIRequestContext,
  prefix: string,
): Promise<TestAccount> {
  const account = makeAccount(prefix)
  await apiRegister(request, account)
  const token = await apiLogin(request, account)
  await loginByToken(page, account, token)
  return account
}

/** 清空该账号的全部行程（用例收尾清理，避免影响后续断言） */
export async function clearItinerary(request: APIRequestContext, account: TestAccount): Promise<void> {
  const token = await apiLogin(request, account)
  const list = await request.get(`${API_BASE}/itinerary`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const body = await list.json()
  for (const item of body.data?.items ?? []) {
    await request.delete(`${API_BASE}/itinerary/${item.id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  }
}

/**
 * 检查后端是否可用（不可用时给出清晰报错，而不是让用例超时）。
 *
 * 注意：不能用 /health——它挂在后端根路径，而前端 8080 的 nginx
 * 只代理 /api/ 前缀，直接请求 /health 会打到静态服务上。
 * 这里用免鉴权的天气接口代替。
 */
export async function assertBackendUp(request: APIRequestContext): Promise<void> {
  const resp = await request.get(`${API_BASE}/weather/current`)
  expect(
    resp.ok(),
    '后端不可用。请先启动服务：docker compose up -d（或本地 uvicorn）',
  ).toBeTruthy()
}
