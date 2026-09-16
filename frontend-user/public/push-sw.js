// Web Push 处理脚本（由 vite-plugin-pwa 生成的 SW 通过 importScripts 注入）。
//
// 为什么要拆成独立文件：PWA 需要自己的 Service Worker 做离线缓存（Workbox 生成），
// 而推送也需要 Service Worker。浏览器对同一 scope 只认**一个** SW，
// 两者不能各注册一个，否则后注册的会顶掉先注册的（推送或离线缓存必坏一个）。
// 做法：生成的 SW 里 importScripts('/push-sw.js')，一个 SW 两种职责。
//
// 注意：文件名不能叫 sw.js——那是 Workbox 生成物的名字，会被覆盖。

self.addEventListener("push", (event) => {
  let payload = { title: "广州天气旅行助手", body: "你有一条新消息", url: "/" }
  try {
    if (event.data) payload = { ...payload, ...event.data.json() }
  } catch (err) {
    // 某些推送服务会发纯文本
    payload.body = (event.data && event.data.text()) || payload.body
  }

  event.waitUntil(
    self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      tag: payload.url, // 同 URL 的通知合并，避免轰炸
      data: { url: payload.url },
    }),
  )
})

self.addEventListener("notificationclick", (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || "/"

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windowList) => {
        // 已有本站窗口则聚焦并跳转，否则新开
        for (const client of windowList) {
          if (client.url.includes(self.location.origin) && "navigate" in client) {
            return client.navigate(url).then(() => client.focus())
          }
        }
        return self.clients.openWindow(url)
      }),
  )
})
