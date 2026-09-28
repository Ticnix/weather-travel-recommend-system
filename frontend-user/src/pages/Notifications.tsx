import { Button, Space, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import NotificationSettings from '../components/NotificationSettings'
import { isLoggedIn } from '../api/auth'

const { Paragraph, Title } = Typography

/**
 * 通知设置独立页（Day 43）。
 *
 * 此前它作为一块内容塞在「我的」页里，和体质偏好、反馈、行程混在一起，
 * 既难找也难扩展。这里拆成独立路由 /notifications，
 * 由用户下拉菜单与「我的」页共同提供入口。
 */
export default function Notifications() {
  const navigate = useNavigate()

  if (!isLoggedIn()) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        <Title level={4} className="jp-serif" style={{ margin: 0 }}>
          通知设置
        </Title>
        <Paragraph style={{ margin: '8px 0 16px', color: 'var(--jp-ink-2)' }}>
          登录后即可管理天气推送与邮件提醒。
        </Paragraph>
        <Button
          type="primary"
          onClick={() => navigate('/login', { state: { from: '/notifications' } })}
        >
          去登录
        </Button>
      </div>
    )
  }

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <NotificationSettings />
    </Space>
  )
}
