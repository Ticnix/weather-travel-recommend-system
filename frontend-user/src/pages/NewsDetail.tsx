import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Alert, Button, Space, Tag, Typography, Divider } from 'antd'
import {
  ArrowLeftOutlined,
  EyeOutlined,
  FireOutlined,
  UserOutlined,
  CalendarOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import { getNews, type NewsItem } from '../api/news'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import { useIsMobile } from '../utils/useIsMobile'

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
  const isMobile = useIsMobile()
  const [news, setNews] = useState<NewsItem | null>(null)
  const [loading, setLoading] = useState(true)
  // 「取不到」可能是没这条资讯，也可能是请求失败：两者提示不能一样，
  // 否则服务出问题时用户会以为这篇文章被下架了
  const [failed, setFailed] = useState(false)

  const load = useCallback(() => {
    if (!id) return
    setLoading(true)
    setFailed(false)
    getNews(Number(id))
      .then(setNews)
      .catch(() => {
        setNews(null)
        setFailed(true)
      })
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        <LoadingState text="正在加载资讯正文…" hint="会一并取回原文内容，通常 1~2 秒" />
      </div>
    )
  }

  if (!news) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        {failed ? (
          <EmptyState
            type="error"
            text="资讯正文没能加载出来"
            hint="这不代表文章被下架，可能只是这次请求失败"
            onRetry={load}
            extra={
              <Button size="small" type="primary" onClick={() => navigate('/news')}>
                返回资讯列表
              </Button>
            }
          />
        ) : (
          <EmptyState
            text="资讯不存在或已下架"
            hint="可以返回列表看看其他气象资讯"
            extra={
              <Button size="small" type="primary" onClick={() => navigate('/news')}>
                返回资讯列表
              </Button>
            }
          />
        )}
      </div>
    )
  }

  const tag = CATEGORY_TAG[news.category] ?? CATEGORY_TAG.news

  return (
    <div className="jp-card" style={{ padding: isMobile ? 14 : '28px 32px' }}>
      <Space style={{ marginBottom: isMobile ? 10 : 16 }} wrap>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/news')} size={isMobile ? 'small' : 'middle'}>
          返回
        </Button>
        {news.source_url && (
          <Button
            type="link"
            size={isMobile ? 'small' : 'middle'}
            icon={<LinkOutlined />}
            href={news.source_url}
            target="_blank"
            rel="noreferrer"
          >
            {isMobile ? '原文' : '在新窗口打开原文'}
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

      {/* 标题：h2（约 30px）在手机上会把首屏占掉一半，改用小一号并收紧行高 */}
      <Title
        level={isMobile ? 4 : 2}
        className="jp-serif"
        style={{
          marginTop: isMobile ? 10 : 16,
          fontSize: isMobile ? 18 : undefined,
          lineHeight: 1.4,
          color: 'var(--jp-ink)',
        }}
      >
        {news.title}
      </Title>

      {/* 作者/时间/阅读数：手机上一行放不下三个，间距收到 12 并允许换行 */}
      <Space
        size={isMobile ? 12 : 24}
        wrap
        style={{ color: 'var(--jp-ink-2)', fontSize: isMobile ? 12 : 13, marginBottom: 8 }}
      >
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
            message={
              isMobile
                ? '以下为自动抓取的原文正文'
                : '以下为自动抓取的原文正文；若希望查看原网页排版，可点击上方「在新窗口打开原文」。'
            }
          />
          <Paragraph
            style={{
              fontSize: isMobile ? 14 : 15,
              lineHeight: isMobile ? 1.85 : 1.9,
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
            message={
              isMobile
                ? '以下为原文页面（内嵌展示）'
                : '以下为该条资讯的原文页面（内嵌展示）；若加载不出来，可点击上方「在新窗口打开原文」。'
            }
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
