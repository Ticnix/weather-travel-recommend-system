import { Component, type ReactNode } from 'react'
import { Button, Result } from 'antd'

interface Props {
  children: ReactNode
  title?: string
  showHome?: boolean
}

interface State {
  error: Error | null
}

/**
 * React 错误边界：子树渲染抛错时兜底，避免整页白屏。
 * 任何一个组件的渲染错误在 React 中会向上冒泡把整棵组件树卸载（白屏），
 * ErrorBoundary 拦截在边界处只替换边界内的内容。
 * 用 class 组件是因为 getDerivedStateFromError / componentDidCatch
 * 至今只有 class 能实现。重试 = 清空 error 重新渲染子树，瞬时错误可恢复。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: unknown): void {
    // 控制台留痕；接入错误上报服务后在此处上报
    console.error('[ErrorBoundary]', error, info)
  }

  private reset = (): void => {
    this.setState({ error: null })
  }

  private goHome = (): void => {
    window.location.href = '/'
  }

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <Result
        status="error"
        title={this.props.title ?? '页面出错了'}
        subTitle="别担心，你的数据没有受影响。可以尝试重试；若反复出现，请回到首页或稍后再来。"
        extra={
          <>
            <Button type="primary" onClick={this.reset}>
              重试
            </Button>
            {this.props.showHome && <Button onClick={this.goHome}>回到首页</Button>}
          </>
        }
      />
    )
  }
}
