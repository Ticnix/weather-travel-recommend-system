import { Typography } from 'antd'

const { Paragraph } = Typography

interface PlaceholderProps {
  title: string
  description: string
}

// 占位页面（日式简洁）
export default function Placeholder({ title, description }: PlaceholderProps) {
  return (
    <div className="jp-card" style={{ padding: '60px 20px', textAlign: 'center' }}>
      <div style={{ fontSize: 52 }}>🍃</div>
      <div className="jp-serif" style={{ fontSize: 20, fontWeight: 600, marginTop: 16, color: 'var(--jp-ink)' }}>
        {title}
      </div>
      <Paragraph style={{ color: 'var(--jp-ink-2)', marginTop: 8 }}>{description}</Paragraph>
    </div>
  )
}
