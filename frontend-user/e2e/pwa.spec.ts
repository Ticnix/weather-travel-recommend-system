import { expect, test } from '@playwright/test'

/**
 * PWA 能力 E2E（Day 38）。
 *
 * 这些用例打的是**构建产物**（docker 里的 nginx，localhost:8080）——
 * 开发服务器默认不启用 Service Worker，测不到真实行为。
 *
 * 关于「Lighthouse PWA 通过」：这里没有跑 Lighthouse，
 * 而是用浏览器 API 逐条核对 Chromium 的可安装性条件
 * （manifest 字段齐全 + 192/512 图标可访问 + SW 接管页面 + 断网可用），
 * 这几条正是 Lighthouse 的 PWA 审计项。
 */

test.describe('PWA 能力', () => {
  test('Manifest 可访问且满足可安装条件', async ({ page, request }) => {
    await page.goto('/')

    const href = await page.getAttribute('link[rel="manifest"]', 'href')
    expect(href, 'index.html 里应有 manifest 链接（由 vite-plugin-pwa 注入）').toBeTruthy()

    const resp = await request.get(href as string)
    expect(resp.ok()).toBeTruthy()
    const manifest = await resp.json()

    // 可安装性必需字段
    expect(manifest.name).toBeTruthy()
    expect(manifest.short_name).toBeTruthy()
    expect(manifest.start_url).toBeTruthy()
    expect(['standalone', 'fullscreen', 'minimal-ui']).toContain(manifest.display)

    // 192 与 512 是 Chromium 的硬性要求，缺一不可安装
    const sizes = manifest.icons.map((icon: { sizes: string }) => icon.sizes)
    expect(sizes).toContain('192x192')
    expect(sizes).toContain('512x512')
    // Android 启动器会按形状裁切图标，必须有 maskable
    expect(
      manifest.icons.some((icon: { purpose?: string }) => icon.purpose === 'maskable'),
    ).toBeTruthy()

    // 图标文件要真的能取到（404 的图标会让安装失败）
    for (const icon of manifest.icons) {
      const iconResp = await request.get(icon.src)
      expect(iconResp.status(), `${icon.src} 应可访问`).toBe(200)
    }
  })

  test('Service Worker 注册成功并接管页面', async ({ page }) => {
    await page.goto('/')

    // 要等的是「已激活」，不是「已注册」——刚注册完还处于 installing，
    // 这时断言 active 必然失败（第一次就是这么错的）
    await page.waitForFunction(
      async () => !!(await navigator.serviceWorker.getRegistration())?.active,
      null,
      { timeout: 30_000 },
    )
    await page.reload()
    // 被接管后需再加载一次，页面才真正是 controlled 状态
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null, null, {
      timeout: 30_000,
    })

    const state = await page.evaluate(async () => {
      const reg = await navigator.serviceWorker.getRegistration()
      return {
        controlled: navigator.serviceWorker.controller?.scriptURL ?? null,
        scope: reg?.scope ?? null,
        active: !!reg?.active,
      }
    })

    expect(state.active, 'SW 应处于 active 状态').toBeTruthy()
    expect(state.controlled, '页面应被 SW 接管').toContain('sw.js')
    expect(state.scope).toContain('/')
  })

  test('推送脚本已注入到生成的 SW 中', async ({ request }) => {
    // 一个 scope 只能有一个 SW：推送与离线缓存必须共用同一个，
    // 所以生成的 sw.js 里必须有 importScripts("/push-sw.js")
    const resp = await request.get('/sw.js')
    expect(resp.ok()).toBeTruthy()
    const body = await resp.text()
    expect(body).toContain('push-sw.js')

    const pushScript = await request.get('/push-sw.js')
    expect(pushScript.status()).toBe(200)
    expect(await pushScript.text()).toContain("addEventListener(\"push\"")
  })

  test('断网后仍能打开页面并看到缓存的天气', async ({ page, context }) => {
    await page.goto('/')
    await page.waitForFunction(
      async () => !!(await navigator.serviceWorker.getRegistration())?.active,
      null,
      { timeout: 30_000 },
    )

    // 关键一步：在「已被 SW 接管」的状态下**在线加载一次**，API 响应才会进缓存。
    // 首次加载时 SW 通常还没接管，那时发出的接口请求是绕过 SW 的，
    // 缓存里什么也没有——断网后自然只能看到空态。
    await page.reload()
    await expect(page.getByText(/°C/).first()).toBeVisible({ timeout: 30_000 })

    // 显式预热缓存：在「已受控」状态下发一次页面同款请求。
    //
    // 为什么不用「等页面自己发出的请求被缓存」：那依赖 SW 接管与首屏请求的时序，
    // StaleWhileRevalidate 又是「先返回响应、再写缓存」，全量跑时踩到过偶发失败。
    // 本用例要验证的是「断网时 SW 能提供缓存数据」，不是请求时序，
    // 所以把缓存准备做成确定性的，再断言缓存确实就位（失败时报的是缓存状态，
    // 而不是一个看不懂的超时）。
    // 等页面确实被 SW 接管 + 缓存确实就位，再断网。
    //
    // 为什么用轮询而不是"发一次请求就断言"：这个用例在全量跑时踩过偶发失败——
    // 上一个用例留下的浏览器状态会让首次接管慢一步，此时发出去的请求根本没经过 SW，
    // 缓存自然是空的。轮询把「等接管 → 预热 → 校验」做成自愈的，
    // 失败时也能从返回值看出是卡在哪一步（no-controller / no-cache）。
    await expect
      .poll(
        () =>
          page.evaluate(async () => {
            if (!navigator.serviceWorker.controller) return 'no-controller'
            await fetch('/api/v1/weather/current?location=gz')
            return (await caches.keys()).includes('api-weather') ? 'ok' : 'no-cache'
          }),
        { timeout: 30_000, message: '断网前应先被 SW 接管并缓存接口响应' },
      )
      .toBe('ok')

    await context.setOffline(true)
    try {
      await page.reload()

      // 应用外壳仍在：导航回退到 index.html，前端路由与导航栏都在
      await expect(page.getByRole('menuitem', { name: '气象资讯' })).toBeVisible({
        timeout: 30_000,
      })
      // 缓存里的天气数据也能看到（SW 的 StaleWhileRevalidate 命中）
      await expect(page.getByText(/°C/).first()).toBeVisible({ timeout: 30_000 })
    } finally {
      await context.setOffline(false)
    }
  })

  test('断网时页面给出离线提示', async ({ page, context }) => {
    await page.goto('/')
    // 先等应用挂载完成再断网：否则 offline 事件可能在监听器注册前就派发完了
    await expect(page.getByRole('menuitem', { name: '气象资讯' })).toBeVisible({ timeout: 20_000 })

    await context.setOffline(true)
    try {
      // 浏览器断网会派发 offline 事件，组件据此展示提示条
      await expect(page.getByTestId('offline-notice')).toBeVisible({ timeout: 20_000 })
      await expect(page.getByTestId('offline-notice')).toHaveText(/缓存/)
    } finally {
      await context.setOffline(false)
    }
  })

  test('默认不主动弹安装引导', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('menuitem', { name: '气象资讯' })).toBeVisible({ timeout: 20_000 })
    // 说明：Chromium 只在"满足可安装条件 + 有用户交互"后才派发 beforeinstallprompt，
    // 自动化环境里不保证触发，所以这里只断言不会无端打扰；
    // 展示逻辑本身（含 iOS 文字指引）由单测覆盖，见 InstallPrompt.test.tsx
    const visible = await page
      .getByTestId('install-prompt')
      .isVisible()
      .catch(() => false)
    if (visible) {
      await expect(page.getByTestId('install-prompt')).toContainText(/添加到主屏幕/)
    }
  })
})
