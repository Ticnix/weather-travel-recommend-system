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
  BellOutlined,
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
import AlertStreamListener from '../components/AlertStreamListener'
import ErrorBoundary from '../components/ErrorBoundary'
import InstallPrompt from '../components/InstallPrompt'
import OfflineNotice from '../components/OfflineNotice'
import { useIsMobile } from '../utils/useIsMobile'

const { Header, Content, Footer } = Layout
const { Title } = Typography

// 导航项（桌面：顶部横向菜单；标签用全称，说得清楚）
const NAV_ITEMS = [
  { key: '/', icon: <HomeOutlined />, label: '首页' },
  { key: '/chat', icon: <MessageOutlined />, label: 'AI 助手' },
  { key: '/recommend', icon: <CompassOutlined />, label: '智能推荐' },
  { key: '/news', icon: <ReadOutlined />, label: '气象资讯' },
  { key: '/feedback', icon: <CommentOutlined />, label: '意见反馈' },
  { key: '/itinerary', icon: <CalendarOutlined />, label: '我的行程' },
  { key: '/profile', icon: <UserOutlined />, label: '我的' },
]

/**
 * 手机底部导航。
 *
 * 为什么手机要换导航：桌面的横向菜单在 390px 宽的屏幕上会把
 * 品牌名 + 7 个菜单项 + 头像挤成一团（中文还会逐字换行），
 * 所以手机改为「顶部只留品牌 + 底部一级入口」——
 * 底部标签是移动端最不需要学习的交互，且拇指够得着。
 *
 * 只放 6 个主要入口；「意见反馈」从首页快捷入口进，「智能推荐」里的穿搭/排程
 * 都在推荐页内，不必单独占用一个位置。
 */
const BOTTOM_NAV = [
  { key: '/', icon: <HomeOutlined />, label: '首页' },
  { key: '/chat', icon: <MessageOutlined />, label: 'AI 助手' },
  { key: '/recommend', icon: <CompassOutlined />, label: '推荐' },
  { key: '/news', icon: <ReadOutlined />, label: '资讯' },
  { key: '/itinerary', icon: <CalendarOutlined />, label: '行程' },
  { key: '/profile', icon: <UserOutlined />, label: '我的' },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const isMobile = useIsMobile()
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
    <Layout
      style={{ minHeight: '100vh', background: 'transparent' }}
      className={isMobile ? 'jp-has-bottom-nav' : undefined}
    >
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          // 手机：品牌简短、留白收紧，把宽度留给内容
          padding: isMobile ? '0 12px' : '0 24px',
          height: isMobile ? 54 : 64,
          background: 'rgba(255, 253, 249, 0.85)',
          backdropFilter: 'blur(10px)',
          borderBottom: '1px solid var(--jp-border)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <Space onClick={() => navigate('/')} style={{ cursor: 'pointer' }} size={8}>
          <span style={{ fontSize: isMobile ? 20 : 24 }}>🌤️</span>
          <Title
            level={4}
            style={{
              margin: 0,
              color: 'var(--jp-ink)',
              fontSize: isMobile ? 16 : undefined,
              whiteSpace: 'nowrap',
            }}
            className="jp-serif"
          >
            {isMobile ? '天气助手' : '广州天气旅行助手'}
          </Title>
        </Space>
        <Space size={isMobile ? 8 : 16} align="center">
          {/* 横向菜单只在桌面出现：手机上它会把顶栏挤爆（见 BOTTOM_NAV 注释） */}
          <div className="jp-hide-mobile">
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
          </div>
          {loggedIn ? (
            <Dropdown
              menu={{
                items: [
                  { key: 'profile', label: '我的', onClick: () => navigate('/profile') },
                  {
                    key: 'notifications',
                    label: '通知设置',
                    icon: <BellOutlined />,
                    onClick: () => navigate('/notifications'),
                  },
                  {
                    key: 'analysis',
                    label: '天气趋势',
                    onClick: () => navigate('/analysis'),
                  },
                  {
                    key: 'my-knowledge',
                    label: '我的知识库',
                    onClick: () => navigate('/my-knowledge'),
                  },
                  { type: 'divider' },
                  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
                ],
              }}
            >
              <Space style={{ cursor: 'pointer' }}>
                <Avatar
                  size={isMobile ? 28 : 32}
                  src={user?.avatar || undefined}
                  icon={<UserOutlined />}
                  style={{ background: !user?.avatar ? 'var(--jp-indigo)' : undefined, color: '#fffdf9' }}
                />
                {/* 昵称在手机上省掉：顶栏宽度优先留给品牌和头像 */}
                <span className="jp-hide-mobile" style={{ color: 'var(--jp-ink)' }}>
                  {user?.nickname || user?.username || '我的'}
                </span>
              </Space>
            </Dropdown>
          ) : (
            <Button
              type="primary"
              size={isMobile ? 'small' : 'middle'}
              onClick={() => navigate('/login', { state: { from: '/profile' } })}
            >
              登录
            </Button>
          )}
        </Space>
      </Header>

      {/* 天气预警实时通道：全站一个实例，收到预警弹出提醒 */}
      <AlertStreamListener />

      {/* 离线提示 + 安装引导（与内容区同宽对齐）。
          注意容器本身**不能留固定留白**：这两个组件都会在运行中自行隐藏
          （网络恢复、用户点了「暂不」），写死 padding-top 会在它们隐藏后
          剩一条空白，看着像页面坏了。间距改由 CSS 给"可见的子元素"加。 */}
      <div className="jp-notice-area">
        <OfflineNotice />
        <InstallPrompt />
      </div>

      <Content
        className="jp-page"
        style={{ padding: '28px 24px', maxWidth: 1100, width: '100%', margin: '0 auto' }}
      >
        {/* 页面级错误边界：单个页面崩溃时只替换内容区，导航仍然可用 */}
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </Content>

      <Footer
        style={{
          textAlign: 'center',
          color: 'var(--jp-ink-3)',
          background: 'transparent',
          borderTop: '1px solid var(--jp-border)',
        }}
      >
        <span style={{ fontSize: 12 }}>
          基于气象大数据的 AI 出行推荐系统 · 广州
        </span>
      </Footer>

      {/* 手机底部导航（桌面隐藏，由 CSS 控制） */}
      {isMobile && (
        <nav className="jp-bottom-nav">
          {BOTTOM_NAV.map((item) => (
            <div
              key={item.key}
              className={`jp-bottom-nav-item${
                selectedKey === item.key || (item.key === '/' && location.pathname === '/')
                  ? ' is-active'
                  : ''
              }`}
              onClick={() => navigate(item.key)}
            >
              {item.icon}
              <span>{item.label}</span>
            </div>
          ))}
        </nav>
      )}
    </Layout>
  )
}
