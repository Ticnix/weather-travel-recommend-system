import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// 品牌色与站点主色保持一致（manifest、地址栏、开屏背景都用它）
const BRAND = '#3b5b8c'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // 新版本 SW 装好即接管，不弹「发现新版本」——本项目不是内容型应用，
      // 用户没耐心处理更新提示
      registerType: 'autoUpdate',
      // 由插件注入注册脚本，业务代码里不再手写 navigator.serviceWorker.register
      injectRegister: 'auto',
      manifest: {
        name: '广州天气旅行助手',
        short_name: '天气助手',
        description: '天气查询、穿搭建议、行程规划与天气预警推送的一站式助手',
        lang: 'zh-CN',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: BRAND,
        theme_color: BRAND,
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          {
            src: '/icons/maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            // maskable：Android 各家启动器会按自己的形状裁切，
            // 图标内容已缩到 62% 留出安全区
            purpose: 'maskable',
          },
        ],
      },
      workbox: {
        // 注意把 gif 也带上：加载图标是 gif，漏掉它的话断网时图标会裂成空白，
        // 而"加载中"恰恰是最可能发生在弱网/离线场景下的一屏
        globPatterns: ['**/*.{js,css,html,svg,png,gif,webp,ico,woff,woff2}'],
        // 默认上限 2MB，大 chunk 会被静默漏掉，提到 3MB
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024,
        // SPA 路由回退：断网时任意前端路由都能拿到应用外壳（否则刷新子路由会 404）
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        cleanupOutdatedCaches: true,
        // 关键：把 Web Push 处理脚本注进生成的 SW。
        // 同一 scope 只能有一个 SW，推送与离线缓存必须合并，不能各注册一个
        importScripts: ['/push-sw.js'],
        runtimeCaching: [
          {
            // 天气/首页数据：弱网下"先给缓存、同时后台更新"——
            // 旧数据也比白屏强，等新数据回来界面会自动刷新
            urlPattern: ({ url, request }) =>
              request.method === 'GET' && /^\/api\/v1\/(weather|home)\//.test(url.pathname),
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-weather',
              expiration: { maxEntries: 60, maxAgeSeconds: 60 * 60 * 6 },
            },
          },
          {
            // 其余 GET 接口：网络优先，断网回退缓存（写操作一律不缓存）
            urlPattern: ({ url, request }) =>
              request.method === 'GET' && url.pathname.startsWith('/api/v1/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-other',
              networkTimeoutSeconds: 5,
              expiration: { maxEntries: 80, maxAgeSeconds: 60 * 60 },
            },
          },
        ],
      },
      devOptions: {
        // 开发时不启用 SW：否则调试时分不清拿到的是缓存还是接口返回
        enabled: false,
      },
    }),
  ],
  server: {
    port: 5173,
    // 监听所有网卡：手机/平板要访问这个 dev 服务器时必需
    // （只监听 localhost 的话，隧道或局域网都连不进来）
    host: true,
    // Vite 默认会拦掉 Host 不匹配的请求（防 DNS rebinding 攻击）。
    // 手机通过 Cloudflare 隧道访问时 Host 是 xxx.trycloudflare.com，
    // 而 quick tunnel 的域名每次重启都会变，所以按域名后缀整段放行。
    // 注意：只放行隧道域名，不要图省事写成 true（那等于把校验全关掉）。
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      // 开发模式将 /api 代理到本地后端，避免跨域。
      // 默认 8001 是本机另起的 uvicorn；跑 Docker 后端时用
      // VITE_API_TARGET=http://127.0.0.1:8000 覆盖（见根目录 dev-user.ps1）
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
