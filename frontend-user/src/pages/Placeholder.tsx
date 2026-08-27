import { Card, Empty, Typography } from 'antd'

const { Title, Paragraph } = Typography

interface PlaceholderProps {
  title: string
  description: string
}

// 占位页面：为后续（Day 18）功能预留入口
export default function Placeholder({ title, description }: PlaceholderProps) {
  return (
    <Card style={{ borderRadius: 16 }}>
      <Empty
        style={{ padding: '40px 0' }}
        description={
          <div>
            <Title level={4}>{title}</Title>
            <Paragraph type="secondary">{description}</Paragraph>
          </div>
        }
      />
    </Card>
  )
}
