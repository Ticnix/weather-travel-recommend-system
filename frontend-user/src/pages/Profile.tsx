import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Avatar,
  Button,
  Card,
  Col,
  Empty,
  List,
  Row,
  Space,
  Tag,
  Typography,
} from 'antd'
import {
  UserOutlined,
  MessageOutlined,
  EditOutlined,
  SendOutlined,
  LogoutOutlined,
  ClockCircleOutlined,
  CommentOutlined,
  CalendarOutlined,
  BellOutlined,
} from '@ant-design/icons'
import { listMyFeedback, type FeedbackItem } from '../api/feedback'
import { listItinerary, type ItineraryItem } from '../api/itinerary'
import {
  clearAuth,
  fetchMe,
  getStoredUser,
  isLoggedIn,
  type AuthUser,
} from '../api/auth'
import LoadingState from '../components/LoadingState'
import EmptyState from '../components/EmptyState'
import MapLink from '../components/MapLink'
import PreferenceSettings from '../components/PreferenceSettings'

const { Title, Paragraph, Text } = Typography

const STATUS_META: Record<FeedbackItem['status'], { color: string; label: string }> = {
  pending: { color: 'gold', label: '待处理' },
  processing: { color: 'blue', label: '处理中' },
  resolved: { color: 'green', label: '已解决' },
  closed: { color: 'default', label: '已关闭' },
}

export default function Profile() {
  const navigate = useNavigate()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [feedback, setFeedback] = useState<FeedbackItem[]>([])
  const [itinerary, setItinerary] = useState<ItineraryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [loggingOut, setLoggingOut] = useState(false)
  // 反馈与行程各自的 catch 原来只是把列表置空，
  // 页面于是显示"暂无反馈记录/还没有行程安排"——把"没取到"说成了"你没有"
  const [failed, setFailed] = useState(false)

  const loggedIn = isLoggedIn()

  const load = useCallback(() => {
    if (!loggedIn) {
      setLoading(false)
      return
    }
    setLoading(true)
    setFailed(false)
    // 优先用本地存储，再拉最新
    setUser(getStoredUser())
    let failedAny = false
    Promise.all([
      fetchMe()
        .then(setUser)
        .catch(() => {
          failedAny = true
        }),
      listMyFeedback()
        .then((res) => setFeedback(res.items))
        .catch(() => {
          failedAny = true
          setFeedback([])
        }),
      // 「我的」页直接展示行程概览，此前这里只是一块写着"开发中"的占位
      listItinerary()
        .then((res) => setItinerary(res.items))
        .catch(() => {
          failedAny = true
          setItinerary([])
        }),
    ]).finally(() => {
      setFailed(failedAny)
      setLoading(false)
    })
  }, [loggedIn])

  useEffect(() => {
    load()
  }, [load])

  const handleLogout = () => {
    setLoggingOut(true)
    clearAuth()
    setUser(null)
    setFeedback([])
    setItinerary([])
    setLoggingOut(false)
    navigate('/')
  }

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      {/* 用户信息卡 */}
      <div className="jp-card" style={{ padding: 24 }}>
        <Row align="middle" gutter={20}>
          <Col>
            <Avatar
              size={64}
              src={user?.avatar || undefined}
              icon={<UserOutlined />}
              style={{ background: !user?.avatar ? 'var(--jp-indigo)' : undefined, color: '#fffdf9' }}
            />
          </Col>
          <Col flex="1">
            {loggedIn && user ? (
              <>
                <Title level={4} style={{ margin: 0 }} className="jp-serif">
                  {user.nickname || user.username}
                </Title>
                <Text style={{ color: 'var(--jp-ink-2)' }}>
                  @{user.username} · {user.role === 'admin' ? '管理员' : '普通用户'}
                </Text>
              </>
            ) : (
              <>
                <Title level={4} style={{ margin: 0 }} className="jp-serif">
                  未登录
                </Title>
                <Text style={{ color: 'var(--jp-ink-2)' }}>登录后同步你的行程与反馈记录</Text>
              </>
            )}
          </Col>
          <Col>
            {loggedIn ? (
              <Button
                icon={<LogoutOutlined />}
                loading={loggingOut}
                onClick={handleLogout}
              >
                退出登录
              </Button>
            ) : (
              <Space>
                <Button icon={<EditOutlined />} onClick={() => navigate('/login', { state: { from: '/profile' } })}>
                  注册
                </Button>
                <Button
                  type="primary"
                  onClick={() => navigate('/login', { state: { from: '/profile' } })}
                >
                  登录
                </Button>
              </Space>
            )}
          </Col>
        </Row>
      </div>

      {/* 偏好设置（体质 + AI 偏好，合并为一张卡，Day 56/合并版）：
          放页面顶部——它是"系统记住了什么"的入口，比反馈列表更重要 */}
      {loggedIn && <PreferenceSettings />}

      {/* 我的反馈（仅登录可见） */}
      {loggedIn && (
        <div className="jp-card" style={{ padding: 24 }}>
          <Row justify="space-between" align="middle" style={{ marginBottom: 12 }}>
            <div className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
              <MessageOutlined /> 我的反馈
            </div>
            <Button
              size="small"
              type="primary"
              icon={<SendOutlined />}
              onClick={() => navigate('/feedback')}
            >
              新建反馈
            </Button>
          </Row>

          {loading ? (
            <LoadingState compact text="正在加载反馈记录…" hint="同时会拉取最新处理状态" />
          ) : failed ? (
            <EmptyState
              type="error"
              text="反馈记录没能加载出来"
              hint="这不代表你没有反馈记录，可能只是这次请求失败"
              onRetry={load}
            />
          ) : feedback.length === 0 ? (
            <Empty description="暂无反馈记录" style={{ padding: 30 }} />
          ) : (
            <List
              dataSource={feedback}
              renderItem={(fb) => (
                <List.Item>
                  <Card
                    className="jp-card"
                    style={{ width: '100%' }}
                    styles={{ body: { padding: 16 } }}
                  >
                    <Space direction="vertical" size={6} style={{ width: '100%' }}>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Space size={6}>
                          <Tag color={STATUS_META[fb.status].color}>
                            {STATUS_META[fb.status].label}
                          </Tag>
                          {fb.reply && <Tag color="green">已回复</Tag>}
                        </Space>
                        <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                          {fb.created_at?.slice(0, 10)}
                        </Text>
                      </Space>

                      {/* 反馈内容：长文本可点击「展开」查看全文 */}
                      <Paragraph
                        style={{ margin: 0, color: 'var(--jp-ink)' }}
                        ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
                      >
                        {fb.content}
                      </Paragraph>

                      {fb.contact && (
                        <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                          联系方式：{fb.contact}
                        </Text>
                      )}

                      {/* 管理员回复：这是用户最关心的信息，有则醒目展示 */}
                      {fb.reply ? (
                        <div
                          style={{
                            marginTop: 6,
                            padding: '10px 14px',
                            borderRadius: 10,
                            background: 'rgba(90,125,90,0.09)',
                            borderLeft: '3px solid #5a7d5a',
                          }}
                        >
                          <Space size={8} style={{ marginBottom: 4 }}>
                            <Text style={{ fontWeight: 600, color: '#5a7d5a', fontSize: 13 }}>
                              <CommentOutlined /> 管理员回复
                            </Text>
                            {fb.reply_at && (
                              <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                                {fb.reply_at.slice(0, 16).replace('T', ' ')}
                              </Text>
                            )}
                          </Space>
                          <Paragraph
                            style={{
                              margin: 0,
                              color: 'var(--jp-ink)',
                              whiteSpace: 'pre-wrap',
                              fontSize: 13.5,
                            }}
                          >
                            {fb.reply}
                          </Paragraph>
                        </div>
                      ) : (
                        <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                          <ClockCircleOutlined /> 管理员正在处理，回复后会显示在这里
                        </Text>
                      )}
                    </Space>
                  </Card>
                </List.Item>
              )}
            />
          )}
        </div>
      )}

      {/* 我的行程概览（数据来自 /itinerary，此前是"开发中"占位） */}
      <div className="jp-card" style={{ padding: 24 }}>
        <Row justify="space-between" align="middle" style={{ marginBottom: 12 }}>
          <div
            className="jp-serif"
            style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}
          >
            <CalendarOutlined /> 我的行程
          </div>
          <Button size="small" onClick={() => navigate('/itinerary')}>
            查看全部
          </Button>
        </Row>

        {!loggedIn ? (
          <Paragraph style={{ margin: 0, color: 'var(--jp-ink-2)' }}>
            登录后可查看行程安排，并获得结合天气的出行提醒。
          </Paragraph>
        ) : loading ? (
          <LoadingState compact text="正在加载行程列表…" hint="顺带比对每段行程当天的天气" />
        ) : failed ? (
          <EmptyState
            type="error"
            text="行程没能加载出来"
            hint="可能只是这次请求失败，点重试即可"
            onRetry={load}
          />
        ) : itinerary.length === 0 ? (
          <Empty description="还没有行程安排" style={{ padding: 16 }}>
            <Button type="primary" size="small" onClick={() => navigate('/itinerary')}>
              去添加行程
            </Button>
          </Empty>
        ) : (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            {itinerary.slice(0, 5).map((it) => (
              <div
                key={it.id}
                style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}
              >
                <Tag color="blue" icon={<CalendarOutlined />} style={{ margin: 0 }}>
                  {it.date}
                </Tag>
                {it.start_time && <Tag style={{ margin: 0 }}>{it.start_time}</Tag>}
                <Text style={{ color: 'var(--jp-ink)', fontWeight: 600 }}>
                  <MapLink name={it.title} />
                </Text>
                {it.location && it.location !== it.title && (
                  <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>
                    <MapLink name={it.location} />
                  </Text>
                )}
              </div>
            ))}
            {itinerary.length > 5 && (
              <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>
                共 {itinerary.length} 条，此处仅展示前 5 条
              </Text>
            )}
          </Space>
        )}
      </div>

      {/* 通知设置入口（Day 43）：内容已拆为独立页面，这里只留跳转，不再与「我的」内容混排 */}
      {loggedIn && (
        <div className="jp-card" style={{ padding: 24 }}>
          <Row justify="space-between" align="middle" gutter={16}>
            <Col flex="1">
              <div
                className="jp-serif"
                style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}
              >
                <BellOutlined /> 通知设置
              </div>
              <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
                管理天气推送、邮件提醒，绑定接收邮箱
              </Text>
            </Col>
            <Col>
              <Button type="primary" onClick={() => navigate('/notifications')}>
                前往设置
              </Button>
            </Col>
          </Row>
        </div>
      )}

      {/* 偏好设置已并入顶部「我的偏好」卡（体质 + AI 偏好合一） */}
    </Space>
  )
}
