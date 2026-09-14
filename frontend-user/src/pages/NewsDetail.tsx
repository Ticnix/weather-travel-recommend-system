import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Alert, Button, Skeleton, Space, Tag, Typography, Divider } from 'antd'
import {
  ArrowLeftOutlined,
  EyeOutlined,
  FireOutlined,
  UserOutlined,
  CalendarOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import { getNews, type NewsItem } from '../api/news'

const { Title, Paragraph, Text } = Typography

// 分类 → 标签颜色/文案
const CATEGORY_TAG: Record<string, { color: string; text: string }> = {
  notice: { color: 'magenta', text: '官方公告' },
  alert: { color: 'red', text: '气象预警' },
  news: { color: 'cyan', text: '气象资讯' },
}

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

  const tag = CATEGORY_TAG[news.category] ?? CATEGORY_TAG.news

  return (
    <div className="jp-card" style={{ padding: '28px 32px' }}>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/news')}>
          返回
        </Button>
        {news.source_url && (
          <Button
            type="link"
            icon={<LinkOutlined />}
            href={news.source_url}
            target="_blank"
            rel="noreferrer"
          >
            在新窗口打开原文
          </Button>
        )}
      </Space>

      <Space size={10} wrap>
        <Tag color={tag.color}>{tag.text}</Tag>
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

      {/* 正文区优先级：
          1) 已抓取原文正文 → 直接渲染（多数新闻站禁止 iframe 内嵌，这样最稳）
          2) 有原文链接 → iframe 内嵌
          3) 兜底 → 纯文本 content */}
      {news.full_text ? (
        <>
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 12 }}
            message="以下为自动抓取的原文正文；若希望查看原网页排版，可点击上方「在新窗口打开原文」。"
          />
          <Paragraph
            style={{
              fontSize: 15,
              lineHeight: 1.9,
              color: 'var(--jp-ink)',
              whiteSpace: 'pre-wrap',
              margin: 0,
            }}
          >
            {news.full_text}
          </Paragraph>
        </>
      ) : news.source_url ? (
        <>
          {/* 采集类资讯（如中央气象台预警）：内嵌原文，直接浏览完整内容 */}
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="以下为该条资讯的原文页面（内嵌展示）；若加载不出来，可点击上方「在新窗口打开原文」。"
          />
          <iframe
            src={news.source_url}
            title={news.title}
            style={{
              width: '100%',
              height: '74vh',
              border: '1px solid var(--jp-border)',
              borderRadius: 12,
              background: '#fff',
            }}
          />
        </>
      ) : (
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
      )}
    </div>
  )
}
