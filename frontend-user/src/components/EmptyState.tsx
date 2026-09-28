import { Button, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'

const { Text } = Typography

interface Props {
  /** empty：本来就没有数据；error：请求失败/没查到，需要用户知道"这不是没数据" */
  type?: 'empty' | 'error'
  /** 一句话说清结果（如「南沙区没检索到候选地点」） */
  text: string
  /** 提供下一步动作的解释（如「换个区名再试」） */
  hint?: string
  /** 重试回调；失败态建议都给一个 */
  onRetry?: () => void
  retryText?: string
  /** 附加动作按钮（如「去添加行程」） */
  extra?: ReactNode
}

/**
 * 统一的「没有结果 / 出错了」提示。
 *
 * 关键设计：**空结果和失败必须分开**。
 * 两者都显示"暂无数据"时，用户会以为是自己没数据，而不是"功能没跑起来"——
 * 这正是「说了南沙区却没反应」那类问题的观感来源：
 * 页面看起来一切正常，只是内容不对。
 *
 * 所以 error 态一律给原因 + 重试入口；empty 态才只说明现状。
 */
export default function EmptyState({
  type = 'empty',
  text,
  hint,
  onRetry,
  retryText = '重新加载',
  extra,
}: Props) {
  const isError = type === 'error'
  return (
    <div
      data-testid={isError ? 'error-state' : 'empty-state'}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
        padding: '24px 16px',
        textAlign: 'center',
      }}
    >
      <span style={{ fontSize: 30 }} aria-hidden="true">
        {isError ? '⚠️' : '🗒️'}
      </span>
      <Text
        style={{
          fontSize: 14,
          fontWeight: 600,
          color: isError ? 'var(--jp-vermilion)' : 'var(--jp-ink)',
        }}
      >
        {text}
      </Text>
      {hint && (
        <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)', maxWidth: 420, lineHeight: 1.7 }}>
          {hint}
        </Text>
      )}
      {(onRetry || extra) && (
        <div style={{ marginTop: 4, display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          {onRetry && (
            <Button size="small" icon={<ReloadOutlined />} onClick={onRetry}>
              {retryText}
            </Button>
          )}
          {extra}
        </div>
      )}
    </div>
  )
}
