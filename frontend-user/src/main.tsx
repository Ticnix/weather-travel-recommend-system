import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'antd/dist/reset.css'
import './styles/jp-clean.css'
import ErrorBoundary from './components/ErrorBoundary'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* 全局错误边界：任何未被局部边界接住的渲染异常都在这里兜底，避免白屏 */}
    <ErrorBoundary showHome>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
