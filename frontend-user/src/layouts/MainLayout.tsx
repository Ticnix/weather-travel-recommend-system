import { Layout, Menu, Space, Typography, theme } from 'antd'
import {
  HomeOutlined,
  MessageOutlined,
  ReadOutlined,
  CalendarOutlined,
  UserOutlined,
  CloudOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

const { Header, Content, Footer } = Layout
const { Title } = Typography

// 导航项：预留后续功能入口（资讯、行程等 Day 18 接入）
const NAV_ITEMS = [
  { key: '/', icon: <HomeOutlined />, label: '首页' },
  { key: '/chat', icon: <MessageOutlined />, label: 'AI 助手' },
  { key: '/news', icon: <ReadOutlined />, label: '气象资讯' },
  { key: '/itinerary', icon: <CalendarOutlined />, label: '我的行程' },
  { key: '/profile', icon: <UserOutlined />, label: '我的' },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()

  // 选中当前路由对应的菜单项
  const selectedKey = NAV_ITEMS.find((item) =>
    item.key === '/' ? location.pathname === '/' : location.pathname.startsWith(item.key),
  )?.key

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 24px',
          background: 'rgba(255,255,255,0.9)',
          backdropFilter: 'blur(8px)',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
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
          <CloudOutlined style={{ fontSize: 26, color: token.colorPrimary }} />
          <Title level={4} style={{ margin: 0 }}>
            广州天气旅行助手
          </Title>
        </Space>
        <Menu
          mode="horizontal"
          selectedKeys={selectedKey ? [selectedKey] : []}
          items={NAV_ITEMS}
          onClick={(e) => navigate(e.key)}
          style={{ flex: 1, justifyContent: 'flex-end', borderBottom: 'none', minWidth: 0 }}
        />
      </Header>

      <Content style={{ padding: '24px', maxWidth: 1200, width: '100%', margin: '0 auto' }}>
        <Outlet />
      </Content>

      <Footer style={{ textAlign: 'center', color: token.colorTextTertiary }}>
        基于气象大数据的 AI 出行推荐系统 · 广州
      </Footer>
    </Layout>
  )
}
