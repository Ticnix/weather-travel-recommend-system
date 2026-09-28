import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import LoadingState from './LoadingState'
import EmptyState from './EmptyState'

/**
 * 这两个组件的存在理由只有一句：**别让用户面对一个没有任何解释的空白/转圈**。
 * 所以断言也围绕这句话——等待要说明"在做什么、要等多久"，
 * 取不到要说清"是失败还是真的没有数据"。
 */
describe('LoadingState', () => {
  it('告诉用户在做什么、大概要等多久', () => {
    render(<LoadingState text="正在为你生成行程…" hint="通常 10~30 秒，请先别关掉页面" />)

    expect(screen.getByTestId('loading-state')).toBeInTheDocument()
    expect(screen.getByText('正在为你生成行程…')).toBeInTheDocument()
    expect(screen.getByText('通常 10~30 秒，请先别关掉页面')).toBeInTheDocument()
  })

  it('不强求补充说明', () => {
    render(<LoadingState text="正在加载…" />)

    expect(screen.getByText('正在加载…')).toBeInTheDocument()
  })
})

describe('EmptyState', () => {
  it('失败态给原因与重试入口', async () => {
    const onRetry = vi.fn()
    render(
      <EmptyState
        type="error"
        text="行程没能加载出来"
        hint="这不是「你没有行程」，而是这次请求失败了"
        onRetry={onRetry}
      />,
    )

    expect(screen.getByTestId('error-state')).toBeInTheDocument()
    expect(screen.getByText(/这不是「你没有行程」/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /重新加载/ }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('空态与失败态可区分', () => {
    render(<EmptyState text="还没有行程安排" />)

    // 两种状态的 testid 不同：把"没取到"渲染成"你没有"是这里最要避免的错
    expect(screen.getByTestId('empty-state')).toBeInTheDocument()
    expect(screen.queryByTestId('error-state')).not.toBeInTheDocument()
  })

  it('可以带一个附加动作按钮', () => {
    render(
      <EmptyState
        text="资讯不存在或已下架"
        extra={<button type="button">返回资讯列表</button>}
      />,
    )

    expect(screen.getByRole('button', { name: '返回资讯列表' })).toBeInTheDocument()
  })
})
