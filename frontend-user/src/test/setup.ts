/**
 * 测试全局初始化（由 vitest.config.ts 的 setupFiles 自动加载）。
 *
 * jsdom 只实现了浏览器 API 的一部分，而 antd / ECharts 这类组件
 * 会用到 matchMedia、ResizeObserver 等接口——不补上就会在
 * 「渲染组件」时报 `xxx is not a function`，且错误位置与真实原因无关，
 * 很难排查。所以统一在这里打桩。
 */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// 每个用例结束后卸载已渲染的组件，避免 DOM 在用例之间串味
afterEach(() => {
  cleanup()
})

// antd 的响应式栅格依赖 matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
})

// antd 的部分组件（如表格、折叠面板）依赖 ResizeObserver
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (!('ResizeObserver' in window)) {
  Object.defineProperty(window, 'ResizeObserver', {
    writable: true,
    value: ResizeObserverStub,
  })
}

// 滚动相关 API 在 jsdom 中不存在，ForecastList 的「定位到今天」会用到
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = vi.fn() as unknown as typeof Element.prototype.scrollTo
}
