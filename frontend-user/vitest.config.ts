import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

/**
 * Vitest 配置（前端单元测试 + 组件测试）。
 *
 * 与 vite.config.ts 分开的原因：
 * vite.config.ts 里的 dev server / proxy 配置对测试无用，
 * 而测试需要 jsdom 环境、setup 文件、覆盖率口径等专属配置，
 * 混在一起会让两边都变难读。
 */
export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom：在 Node 里模拟浏览器 DOM，组件测试必需
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // 不开启 globals：显式 import { describe, it, expect } 更清晰，
    // 也省去改 tsconfig types 的麻烦
    globals: false,
    // 默认 5s 在并行跑 + 本机跑着 docker 时不够用（组件渲染明显变慢），
    // 会出现「单跑必过、全量偶挂」的假失败；放宽比事后重跑靠谱
    testTimeout: 20_000,
    hookTimeout: 20_000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      // 本机 IDE 会拦截 Node 的递归删除（safe-delete shim），
      // 导致 vitest 清空 coverage/ 目录时报错；报告文件本身每次都会重新生成，关掉即可
      clean: false,
      // 统计口径：只统计「适合单元测试」的那部分代码
      //   utils/**      纯函数（天气映射、格式化），要求高覆盖
      //   components/** 组件渲染逻辑
      //   api/http.ts   请求拦截器——鉴权注入/响应解包/错误提示，最容易出 bug 的地方
      include: ['src/utils/**', 'src/components/**', 'src/api/http.ts'],
      exclude: [
        'src/**/*.d.ts',
        'src/test/**',
        'src/**/*.{test,spec}.{ts,tsx}',
        // 依赖 md-editor 等重型依赖，渲染成本高、收益低，交给 E2E
        'src/components/NotePanel.tsx',
      ],
      // 页面级（pages/**）、布局（layouts/**）与其余 api/*.ts 不纳入统计：
      // 前者依赖路由与全局状态，由 Playwright E2E 覆盖更贴近真实；
      // 后者基本只有一行请求转发，单测价值低。
    },
  },
})
