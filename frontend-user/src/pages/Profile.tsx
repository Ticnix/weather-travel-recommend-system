import { useEffect, useState } from 'react'
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
} from '@ant-design/icons'
import { listMyFeedback, type FeedbackItem } from '../api/feedback'
import {
  clearAuth,
  fetchMe,
  getStoredUser,
  isLoggedIn,
  type AuthUser,
} from '../api/auth'

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
  const [loading, setLoading] = useState(true)
  const [loggingOut, setLoggingOut] = useState(false)

  const loggedIn = isLoggedIn()

  useEffect(() => {
    if (!loggedIn) {
      setLoading(false)
      return
    }
    // 优先用本地存储，再拉最新
    setUser(getStoredUser())
    Promise.all([
      fetchMe().then(setUser).catch(() => {}),
      listMyFeedback()
        .then((res) => setFeedback(res.items))
        .catch(() => setFeedback([])),
    ]).finally(() => setLoading(false))
  }, [loggedIn])

  const handleLogout = () => {
    setLoggingOut(true)
    clearAuth()
    setUser(null)
    setFeedback([])
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
            <Text style={{ color: 'var(--jp-ink-2)' }}>加载中…</Text>
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

      {/* 预留：我的行程 / 推荐收藏 */}
      <div className="jp-card" style={{ padding: 24 }}>
        <div className="jp-serif" style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: 'var(--jp-ink)' }}>
          我的行程
        </div>
        <Paragraph style={{ margin: 0, color: 'var(--jp-ink-2)' }}>
          结合天气的出行提醒、收藏的路线将在登录后展示（开发中）。
        </Paragraph>
      </div>
    </Space>
  )
}
