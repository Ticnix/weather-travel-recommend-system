import { useState } from 'react'
import { Alert, Button, Input, Space, Tag, Typography, message } from 'antd'
import { MailOutlined } from '@ant-design/icons'
import { updateProfile } from '../api/auth'

const { Text } = Typography

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

interface Props {
  /** 当前已绑定邮箱（null 表示未绑定） */
  boundEmail: string | null
  /** 服务端邮件通道是否可用（SMTP 已配置） */
  emailConfigured: boolean
  /** 绑定 / 更换 / 解绑成功后通知父组件刷新通道状态 */
  onChanged: () => void
}

/**
 * 邮箱绑定（Day 43）。
 *
 * 此前邮件通道只在发送记录里留一句「用户未绑定邮箱」，
 * 用户既不知道要去哪绑，也不知道绑定有什么用——
 * 这里把「未绑定 → 绑定 → 更换 → 解绑」补成一条完整链路，
 * 并在未绑定时用醒目提示说清「绑定后能收到什么」。
 */
export default function EmailBinding({ boundEmail, emailConfigured, onChanged }: Props) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(boundEmail ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    const v = value.trim()
    if (!v) {
      setError('请输入邮箱地址')
      return
    }
    if (!EMAIL_RE.test(v)) {
      setError('邮箱格式不正确，请检查后重试')
      return
    }
    if (v === boundEmail) {
      setEditing(false)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await updateProfile({ email: v })
      message.success('邮箱绑定成功')
      setEditing(false)
      onChanged()
    } catch {
      // 错误提示由 http 拦截器统一弹出，这里保持编辑态让用户修改
    } finally {
      setSaving(false)
    }
  }

  const unbind = async () => {
    setSaving(true)
    try {
      await updateProfile({ email: null })
      message.success('已解绑邮箱')
      setEditing(false)
      onChanged()
    } catch {
      // 错误提示由 http 拦截器统一弹出
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{ borderTop: '1px solid var(--jp-border)', paddingTop: 14, marginTop: 8 }}>
      <Space align="center" size={8} style={{ marginBottom: 10 }}>
        <MailOutlined style={{ color: 'var(--jp-indigo)' }} />
        <Text style={{ fontWeight: 600, fontSize: 14 }}>邮箱通知</Text>
        {boundEmail ? <Tag color="green">已绑定</Tag> : <Tag color="orange">未绑定</Tag>}
        {/* 已绑定只说明「有收件地址」，服务端没配 SMTP 时照样发不出去，
            两个状态分开显示，避免用户以为绑了就一定能收到 */}
        {!emailConfigured && <Tag color="orange">服务端未配置</Tag>}
      </Space>

      {!boundEmail && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="你还没有绑定邮箱"
          description={
            emailConfigured
              ? '绑定邮箱后，即使没有打开网页，也能通过邮件收到台风预警、暴雨提醒和每日早报。'
              : '绑定邮箱后即可通过邮件接收通知（当前邮件服务尚未配置，绑定后暂不会真正发出）。'
          }
        />
      )}

      {/* 已绑定但服务端没配 SMTP：地址存下了，邮件却发不出去——
          不提示的话用户会一直等一封永远不来的信 */}
      {boundEmail && !emailConfigured && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="邮件服务尚未配置，邮件暂时发不出去"
          description="你的邮箱已保存，但服务端还没有配置 SMTP 发信账号。等管理员配置完成后，邮件通知才会真正生效。"
        />
      )}

      {boundEmail && !editing ? (
        <Space wrap size={12} align="center">
          <Text style={{ fontSize: 13.5, color: 'var(--jp-ink-2)' }}>已绑定：</Text>
          <Text strong style={{ color: 'var(--jp-ink)' }}>
            {boundEmail}
          </Text>
          <Button
            size="small"
            onClick={() => {
              // 进入编辑态时用当前邮箱预填（放在事件里而不是 effect，避免级联渲染）
              setValue(boundEmail ?? '')
              setError(null)
              setEditing(true)
            }}
          >
            更换
          </Button>
          <Button size="small" danger loading={saving} onClick={() => void unbind()}>
            解绑
          </Button>
        </Space>
      ) : (
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          <Space.Compact style={{ width: '100%', maxWidth: 480 }}>
            <Input
              placeholder="请输入邮箱，例如 name@example.com"
              value={value}
              status={error ? 'error' : undefined}
              allowClear
              onChange={(e) => {
                setValue(e.target.value)
                setError(null)
              }}
              onPressEnter={() => void save()}
            />
            <Button type="primary" loading={saving} onClick={() => void save()}>
              {boundEmail ? '保存' : '绑定邮箱'}
            </Button>
            {boundEmail && (
              <Button
                onClick={() => {
                  setEditing(false)
                  setValue(boundEmail)
                  setError(null)
                }}
              >
                取消
              </Button>
            )}
          </Space.Compact>
          {error && (
            <Text type="danger" style={{ fontSize: 12 }}>
              {error}
            </Text>
          )}
        </Space>
      )}
    </div>
  )
}
