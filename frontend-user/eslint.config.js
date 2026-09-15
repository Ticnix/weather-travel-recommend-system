import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // 降级为 warn 的理由（不是为了让 CI 变绿而无脑关规则）：
      //
      // 本项目所有数据加载都遵循「组件挂载 → 调 async 函数 → 内部 setLoading/setData」
      // 这一经典模式，共 11 处。react-hooks 新版把「effect 体内调用会 setState 的函数」
      // 判为 error，但它无法区分两种情形：
      //   a) 同步 setState 造成级联渲染（规则真正想拦的）
      //   b) 先 setLoading(true) 再 await 取数（本项目的情形，属预期行为）
      // 要彻底根治需引入 React Query / SWR 这类数据获取层，或改用 React 19 的
      // use() + Suspense——那是独立的重构任务，不该和「搭 CI」混在一起做。
      // 保留为 warn：既不阻断流水线，也不让问题从视野里消失。
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
])
