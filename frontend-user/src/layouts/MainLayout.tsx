import { Avatar, Button, Dropdown, Layout, Menu, Space, Typography } from 'antd'
import {
  HomeOutlined,
  MessageOutlined,
  ReadOutlined,
  CalendarOutlined,
  UserOutlined,
  CommentOutlined,
  LogoutOutlined,
  CompassOutlined,
} from '@ant-design/icons'
import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  clearAuth,
  fetchMe,
  getStoredUser,
  isLoggedIn,
  type AuthUser,
} from '../api/auth'
import ErrorBoundary from '../components/ErrorBoundary'

const { Header, Content, Footer } = Layout
const { Title } = Typography

// 导航项
const NAV_ITEMS = [
  { key: '/', icon: <HomeOutlined />, label: '首页' },
  { key: '/chat', icon: <MessageOutlined />, label: 'AI 助手' },
  { key: '/recommend', icon: <CompassOutlined />, label: '智能推荐' },
  { key: '/news', icon: <ReadOutlined />, label: '气象资讯' },
  { key: '/feedback', icon: <CommentOutlined />, label: '意见反馈' },
  { key: '/itinerary', icon: <CalendarOutlined />, label: '我的行程' },
  { key: '/profile', icon: <UserOutlined />, label: '我的' },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loggedIn, setLoggedIn] = useState(isLoggedIn())

  useEffect(() => {
    if (!loggedIn) {
      setUser(null)
      return
    }
    setUser(getStoredUser())
    fetchMe().then(setUser).catch(() => {})
  }, [loggedIn])

  const selectedKey = NAV_ITEMS.find((item) =>
    item.key === '/' ? location.pathname === '/' : location.pathname.startsWith(item.key),
  )?.key

  const handleLogout = () => {
    clearAuth()
    setLoggedIn(false)
    setUser(null)
    navigate('/')
  }

  return (
    <Layout style={{ minHeight: '100vh', background: 'transparent' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          height: 64,
          background: 'rgba(255, 253, 249, 0.85)',
          backdropFilter: 'blur(10px)',
          borderBottom: '1px solid var(--jp-border)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <Space
          onClick={() => navigate('/')}
          style={{ cursor: 'pointer' }}
          size={10}
        >
          <span style={{ fontSize: 24 }}>🌤️</span>
          <Title level={4} style={{ margin: 0, color: 'var(--jp-ink)' }} className="jp-serif">
            广州天气旅行助手
          </Title>
        </Space>
        <Space size={16} align="center">
          <Menu
            mode="horizontal"
            selectedKeys={selectedKey ? [selectedKey] : []}
            items={NAV_ITEMS}
            onClick={(e) => navigate(e.key)}
            style={{
              borderBottom: 'none',
              minWidth: 0,
              background: 'transparent',
              fontSize: 15,
            }}
          />
          {loggedIn ? (
            <Dropdown
              menu={{
                items: [
                  { key: 'profile', label: '我的', onClick: () => navigate('/profile') },
                  { type: 'divider' },
                  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
                ],
              }}
            >
              <Space style={{ cursor: 'pointer' }}>
                <Avatar
                  size={32}
                  src={user?.avatar || undefined}
                  icon={<UserOutlined />}
                  style={{ background: !user?.avatar ? 'var(--jp-indigo)' : undefined, color: '#fffdf9' }}
                />
                <span style={{ color: 'var(--jp-ink)' }}>{user?.nickname || user?.username || '我的'}</span>
              </Space>
            </Dropdown>
          ) : (
            <Button type="primary" onClick={() => navigate('/login', { state: { from: '/profile' } })}>
              登录
            </Button>
          )}
        </Space>
      </Header>

      <Content style={{ padding: '28px 24px', maxWidth: 1100, width: '100%', margin: '0 auto' }}>
        {/* 页面级错误边界：单个页面崩溃时只替换内容区，导航仍然可用 */}
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </Content>

      <Footer style={{ textAlign: 'center', color: 'var(--jp-ink-3)', background: 'transparent', borderTop: '1px solid var(--jp-border)' }}>
        <span style={{ fontSize: 12 }}>
          基于气象大数据的 AI 出行推荐系统 · 广州
        </span>
      </Footer>
    </Layout>
  )
}
