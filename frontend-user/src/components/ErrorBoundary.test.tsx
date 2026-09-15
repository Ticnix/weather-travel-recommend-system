import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ErrorBoundary from './ErrorBoundary'

// 渲染期抛错的子组件（受控开关：验证「重试」能否恢复）
let shouldThrow = false
function MaybeBoom() {
  if (shouldThrow) throw new Error('渲染爆炸')
  return <div>内容正常</div>
}

beforeEach(() => {
  shouldThrow = false
  // React 与 componentDidCatch 都会往控制台写错误，测试里静音
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('ErrorBoundary 错误边界', () => {
  it('子树渲染抛错时显示兜底UI而不是白屏', () => {
    shouldThrow = true
    render(
      <ErrorBoundary>
        <MaybeBoom />
      </ErrorBoundary>,
    )

    expect(screen.getByText('页面出错了')).toBeInTheDocument()
    // antd 会给两个字的按钮自动插空格（「重试」→「重 试」），用正则匹配
    expect(screen.getByRole('button', { name: /重\s*试/ })).toBeInTheDocument()
    expect(screen.queryByText('内容正常')).not.toBeInTheDocument()
  })

  it('组件级兜底默认不显示回到首页', () => {
    shouldThrow = true
    render(
      <ErrorBoundary>
        <MaybeBoom />
      </ErrorBoundary>,
    )
    expect(screen.queryByRole('button', { name: '回到首页' })).not.toBeInTheDocument()
  })

  it('showHome 时提供回到首页入口', () => {
    shouldThrow = true
    render(
      <ErrorBoundary showHome>
        <MaybeBoom />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('button', { name: '回到首页' })).toBeInTheDocument()
  })

  it('重试清空错误后恢复子树渲染（瞬时错误可自愈）', async () => {
    const user = userEvent.setup()
    shouldThrow = true
    render(
      <ErrorBoundary>
        <MaybeBoom />
      </ErrorBoundary>,
    )
    expect(screen.getByText('页面出错了')).toBeInTheDocument()

    // 模拟「错误是瞬时的」：重试前把开关关掉
    shouldThrow = false
    await user.click(screen.getByRole('button', { name: /重\s*试/ }))
    expect(screen.getByText('内容正常')).toBeInTheDocument()
  })

  it('支持自定义兜底标题（组件级兜底描述更具体）', () => {
    shouldThrow = true
    render(
      <ErrorBoundary title="天气卡片加载失败">
        <MaybeBoom />
      </ErrorBoundary>,
    )
    expect(screen.getByText('天气卡片加载失败')).toBeInTheDocument()
  })
})
