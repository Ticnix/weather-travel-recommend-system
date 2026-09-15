// Web Push 的 Service Worker：
// - push 事件：收到推送后调用系统通知展示
// - notificationclick：点击通知跳到对应页面（已有窗口则聚焦）
//
// 注意：SW 必须放在 public/（构建时原样拷到 dist 根目录），
// pushManager.subscribe 的 scope 才能注册到整站。

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
      icon: "/favicon.svg",
      badge: "/favicon.svg",
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
