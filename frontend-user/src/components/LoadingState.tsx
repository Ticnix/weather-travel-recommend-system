import { Typography } from 'antd'
import loadingGif from '../assets/loading.gif'

const { Text } = Typography

interface Props {
  /** 主提示：说清"正在做什么"（必填，否则用户只能盯着骨架屏猜） */
  text: string
  /** 补充说明：让用户对等待有预期（等多久、为什么慢） */
  hint?: string
  /** 紧凑模式：卡片内部的小区域用，图标更小、上下留白更少 */
  compact?: boolean
}

/**
 * 统一的加载中提示。
 *
 * 为什么不用 Skeleton 当主力：骨架屏只表达"这里有东西、还没到"，
 * 表达不了"正在做什么"和"要等多久"。而本项目的慢操作很多（大模型生成、
 * 联网搜索、逐日天气比对），用户不知道在等什么时，第一反应是"是不是卡住了"，
 * 于是反复点击或直接关掉页面——文案比骨架屏更能留住人。
 *
 * 骨架屏仍然有用（它预示内容形状），所以两者是搭配关系：
 * 本组件负责"说清楚"，骨架屏负责"占好位"。
 */
export default function LoadingState({ text, hint, compact = false }: Props) {
  return (
    <div
      data-testid="loading-state"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: compact ? 6 : 10,
        padding: compact ? '12px 0' : '28px 16px',
        textAlign: 'center',
      }}
    >
      <img
        src={loadingGif}
        alt=""
        aria-hidden="true"
        style={{ width: compact ? 56 : 88, height: 'auto', display: 'block' }}
      />
      <Text style={{ fontSize: compact ? 13 : 15, fontWeight: 600, color: 'var(--jp-ink)' }}>
        {text}
      </Text>
      {hint && (
        <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)', maxWidth: 420, lineHeight: 1.7 }}>
          {hint}
        </Text>
      )}
    </div>
  )
}
