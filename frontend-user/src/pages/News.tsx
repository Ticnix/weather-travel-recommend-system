import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Col,
  Empty,
  Input,
  Pagination,
  Row,
  Segmented,
  Space,
  Tag,
  Typography,
} from 'antd'
import { EyeOutlined, FireOutlined, SearchOutlined } from '@ant-design/icons'
import { listNews, type NewsCategory, type NewsItem } from '../api/news'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import { useIsMobile } from '../utils/useIsMobile'

const { Paragraph, Text } = Typography
const { Search } = Input

// 分类 → 标签颜色/文案（alert 为采集自中央气象台的真实气象预警）
const CATEGORY_TAG: Record<string, { color: string; text: string }> = {
  notice: { color: 'magenta', text: '公告' },
  alert: { color: 'red', text: '预警' },
  news: { color: 'cyan', text: '资讯' },
}

export default function News() {
  const navigate = useNavigate()
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [category, setCategory] = useState<NewsCategory | 'all'>('all')
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [failed, setFailed] = useState(false)
  const isMobile = useIsMobile()

  const PAGE_SIZE = 12

  const fetchList = async () => {
    setLoading(true)
    setFailed(false)
    try {
      const res = await listNews({
        page,
        page_size: PAGE_SIZE,
        category: category === 'all' ? null : category,
        keyword: keyword || undefined,
      })
      setItems(res.items)
      setTotal(res.total)
    } catch {
      // 原来这里没有 catch：失败时列表保持空 → 页面显示"暂无相关资讯"，
      // 等于把"接口挂了"说成"没有资讯"，还会留下一个未处理的 Promise 异常
      setItems([])
      setTotal(0)
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchList()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, category])

  const handleSearch = (value: string) => {
    setKeyword(value)
    setPage(1)
    // 手动触发：因为 keyword 不在依赖里，避免频繁请求
    setTimeout(fetchList, 0)
  }

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      {/* 标题栏 */}
      <div className="jp-card" style={{ padding: '20px 24px' }}>
        <Row justify="space-between" align="middle" gutter={[16, 16]}>
          <Col>
            <div className="jp-serif" style={{ fontSize: 22, fontWeight: 700, color: 'var(--jp-ink)' }}>
              气象资讯
            </div>
            <Text className="jp-hide-mobile" style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
              获取广州权威气象动态、预警公告与科普知识
            </Text>
          </Col>
          <Col>
            <Search
              placeholder="搜索资讯标题"
              allowClear
              enterButton={<SearchOutlined />}
              onSearch={handleSearch}
              style={{ width: 260 }}
            />
          </Col>
        </Row>
        <div style={{ marginTop: 16 }}>
          <Segmented
            value={category}
            onChange={(v) => {
              setCategory(v as NewsCategory | 'all')
              setPage(1)
            }}
            options={[
              { label: '全部', value: 'all' },
              { label: '气象预警', value: 'alert' },
              { label: '气象资讯', value: 'news' },
              { label: '官方公告', value: 'notice' },
            ]}
          />
        </div>
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="jp-card" style={{ padding: 20 }}>
          {/* 不写「气象资讯」：那是页面标题与导航名，重复出现会干扰文本断言 */}
          <LoadingState text="正在加载资讯列表…" hint="要拉取最新预警、公告与科普内容，通常 1~3 秒" />
        </div>
      ) : failed ? (
        <div className="jp-card" style={{ padding: 20 }}>
          <EmptyState
            type="error"
            text="资讯加载失败"
            hint="气象资讯服务可能暂时不可用；已保留搜索与筛选条件，重试即可"
            onRetry={() => void fetchList()}
          />
        </div>
      ) : items.length === 0 ? (
        <Empty description="暂无相关资讯" style={{ padding: isMobile ? 28 : 60 }} />
      ) : (
        <Row gutter={isMobile ? [12, 12] : [16, 16]}>
          {items.map((item) => (
            <Col key={item.id} xs={24} sm={12} lg={8}>
              {/* 手机上单列铺开，卡片本身再收一档：内边距 18→12、标题 16→15、摘要 13→12.5 */}
              <Card
                className="jp-card"
                hoverable
                onClick={() => navigate(`/news/${item.id}`)}
                styles={{ body: { padding: isMobile ? 12 : 18 } }}
                style={{ height: '100%' }}
              >
                <Space direction="vertical" size={isMobile ? 8 : 10} style={{ width: '100%' }}>
                  <Space size={8}>
                    <Tag
                      color={CATEGORY_TAG[item.category]?.color ?? 'cyan'}
                      style={{ margin: 0 }}
                    >
                      {CATEGORY_TAG[item.category]?.text ?? '资讯'}
                    </Tag>
                    {item.is_top && (
                      <Tag
                        color="red"
                        icon={<FireOutlined />}
                        style={{ margin: 0 }}
                      >
                        置顶
                      </Tag>
                    )}
                  </Space>
                  <div
                    style={{
                      fontSize: isMobile ? 15 : 16,
                      fontWeight: 600,
                      color: 'var(--jp-ink)',
                      lineHeight: 1.4,
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {item.title}
                  </div>
                  {/* 手机上不显示摘要：标题 + 元信息已经是清楚的列表，
                      再多两行摘要只会让每张卡片高出一截（"卡片有点大"的来源） */}
                  <Paragraph
                    className="jp-hide-mobile"
                    style={{
                      margin: 0,
                      fontSize: 13,
                      color: 'var(--jp-ink-2)',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}
                  >
                    {item.content.replace(/<[^>]+>/g, '').slice(0, 80)}
                  </Paragraph>
                  <Row justify="space-between" align="middle">
                    <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                      {item.author ?? '气象台'} · {item.created_at?.slice(0, 10)}
                    </Text>
                    <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                      <EyeOutlined /> {item.view_count}
                    </Text>
                  </Row>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* 分页 */}
      {total > PAGE_SIZE && (
        <div style={{ textAlign: 'center', marginTop: 8 }}>
          <Pagination
            current={page}
            total={total}
            pageSize={PAGE_SIZE}
            onChange={setPage}
            showSizeChanger={false}
          />
        </div>
      )}
    </Space>
  )
}
