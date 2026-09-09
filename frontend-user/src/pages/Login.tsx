import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Divider,
  Form,
  Input,
  Segmented,
  Typography,
} from 'antd'
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons'
import { fetchMe, login, register, saveAuth, type AuthUser } from '../api/auth'

const { Title, Text } = Typography

type Mode = 'login' | 'register'

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [mode, setMode] = useState<Mode>('login')
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const from = (location.state as { from?: string } | null)?.from ?? '/profile'

  const handleFinish = async (values: {
    username: string
    password: string
    nickname?: string
    email?: string
  }) => {
    setLoading(true)
    setError(null)
    try {
      if (mode === 'login') {
        const res = await login(values.username, values.password)
        saveAuth(res)
      } else {
        const user = await register({
          username: values.username,
          password: values.password,
          nickname: values.nickname,
          email: values.email,
        })
        // 注册成功后自动登录
        const res = await login(values.username, values.password)
        saveAuth(res)
        void user
      }
      // 拉取最新用户信息确保存储一致
      try {
        const me: AuthUser = await fetchMe()
        localStorage.setItem('wt_user', JSON.stringify(me))
      } catch {
        /* 已 saveAuth，忽略 */
      }
      navigate(from, { replace: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 420, margin: '40px auto', padding: '0 16px' }}>
      <div className="jp-card" style={{ padding: '32px 28px' }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <span style={{ fontSize: 40 }}>🌤️</span>
          <Title level={3} className="jp-serif" style={{ margin: '12px 0 0', color: 'var(--jp-ink)' }}>
            {mode === 'login' ? '登录' : '注册账号'}
          </Title>
          <Text style={{ color: 'var(--jp-ink-2)' }}>
            广州天气旅行助手 · 你的气象生活伙伴
          </Text>
        </div>

        <div style={{ marginBottom: 20 }}>
          <Segmented
            block
            value={mode}
            onChange={(v) => {
              setMode(v as Mode)
              setError(null)
            }}
            options={[
              { label: '登录', value: 'login' },
              { label: '注册', value: 'register' },
            ]}
          />
        </div>

        {error && (
          <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />
        )}

        <Form form={form} layout="vertical" onFinish={handleFinish} requiredMark={false}>
          <Form.Item
            name="username"
            label={<span style={{ color: 'var(--jp-ink)' }}>用户名</span>}
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, max: 64, message: '用户名 3-64 个字符' },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="3-64 位字符"
              autoComplete="username"
            />
          </Form.Item>

          {mode === 'register' && (
            <Form.Item
              name="nickname"
              label={<span style={{ color: 'var(--jp-ink)' }}>昵称（可选）</span>}
            >
              <Input prefix={<UserOutlined />} placeholder="展示名称，留空则使用用户名" />
            </Form.Item>
          )}

          {mode === 'register' && (
            <Form.Item
              name="email"
              label={<span style={{ color: 'var(--jp-ink)' }}>邮箱（可选）</span>}
              rules={[{ type: 'email', message: '邮箱格式不正确' }]}
            >
              <Input prefix={<MailOutlined />} placeholder="用于接收回复通知" />
            </Form.Item>
          )}

          <Form.Item
            name="password"
            label={<span style={{ color: 'var(--jp-ink)' }}>密码</span>}
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, max: 128, message: '密码至少 6 位' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="至少 6 位"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
          </Form.Item>

          <Button
            type="primary"
            htmlType="submit"
            block
            loading={loading}
            style={{ marginTop: 4 }}
          >
            {mode === 'login' ? '登录' : '注册并登录'}
          </Button>
        </Form>

        <Divider style={{ borderColor: 'var(--jp-border)', margin: '20px 0 12px' }}>
          <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12 }}>体验账号</Text>
        </Divider>
        <Text style={{ color: 'var(--jp-ink-3)', fontSize: 12, display: 'block', textAlign: 'center' }}>
          管理员：admin / admin280517
        </Text>
      </div>
    </div>
  )
}
