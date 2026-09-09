import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Skeleton, Space, Tag, Typography, Divider } from 'antd'
import {
  ArrowLeftOutlined,
  EyeOutlined,
  FireOutlined,
  UserOutlined,
  CalendarOutlined,
} from '@ant-design/icons'
import { getNews, type NewsItem } from '../api/news'

const { Title, Paragraph, Text } = Typography

export default function NewsDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [news, setNews] = useState<NewsItem | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    getNews(Number(id))
      .then(setNews)
      .catch(() => setNews(null))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        <Skeleton active paragraph={{ rows: 10 }} />
      </div>
    )
  }

  if (!news) {
    return (
      <div className="jp-card" style={{ padding: 60, textAlign: 'center' }}>
        <div className="jp-serif" style={{ fontSize: 18, color: 'var(--jp-ink)' }}>资讯不存在或已下架</div>
        <Button
          type="primary"
          style={{ marginTop: 16 }}
          onClick={() => navigate('/news')}
        >
          返回资讯列表
        </Button>
      </div>
    )
  }

  return (
    <div className="jp-card" style={{ padding: '28px 32px' }}>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/news')}>
          返回
        </Button>
      </Space>

      <Space size={10} wrap>
        <Tag color={news.category === 'notice' ? 'magenta' : 'cyan'}>
          {news.category === 'notice' ? '官方公告' : '气象资讯'}
        </Tag>
        {news.is_top && (
          <Tag color="red" icon={<FireOutlined />}>
            置顶
          </Tag>
        )}
      </Space>

      <Title
        level={2}
        className="jp-serif"
        style={{ marginTop: 16, lineHeight: 1.35, color: 'var(--jp-ink)' }}
      >
        {news.title}
      </Title>

      <Space size={24} style={{ color: 'var(--jp-ink-2)', fontSize: 13, marginBottom: 8 }}>
        <Text style={{ color: 'var(--jp-ink-2)' }}>
          <UserOutlined /> {news.author ?? '气象台'}
        </Text>
        <Text style={{ color: 'var(--jp-ink-2)' }}>
          <CalendarOutlined /> {news.created_at?.slice(0, 10)}
        </Text>
        <Text style={{ color: 'var(--jp-ink-2)' }}>
          <EyeOutlined /> {news.view_count} 阅读
        </Text>
      </Space>

      <Divider style={{ borderColor: 'var(--jp-border)' }} />

      <Paragraph
        style={{
          fontSize: 15,
          lineHeight: 1.9,
          color: 'var(--jp-ink)',
          whiteSpace: 'pre-wrap',
          margin: 0,
        }}
      >
        {news.content}
      </Paragraph>
    </div>
  )
}
