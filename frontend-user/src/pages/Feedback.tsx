import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Input,
  Result,
  Space,
  Typography,
} from 'antd'
import {
  SendOutlined,
  MailOutlined,
  BulbOutlined,
} from '@ant-design/icons'
import { createFeedback } from '../api/feedback'

const { Paragraph, Text } = Typography
const { TextArea } = Input

const PRESET_TAGS = [
  '数据不准',
  '功能建议',
  '界面问题',
  '其他',
]

export default function Feedback() {
  const navigate = useNavigate()
  const [content, setContent] = useState('')
  const [contact, setContact] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const handleSubmit = async () => {
    if (!content.trim()) {
      setError('请填写反馈内容')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await createFeedback({ content: content.trim(), contact: contact.trim() || undefined })
      setDone(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  if (done) {
    return (
      <Result
        status="success"
        title="反馈提交成功"
        subTitle="感谢您的反馈，我们会尽快处理。您可以在「我的」页面查看反馈进度。"
        extra={[
          <Button type="primary" key="my" onClick={() => navigate('/profile')}>
            查看我的反馈
          </Button>,
          <Button key="back" onClick={() => navigate('/')}>
            返回首页
          </Button>,
        ]}
      />
    )
  }

  return (
    <Space direction="vertical" size={20} style={{ width: '100%', maxWidth: 760, margin: '0 auto' }}>
      <div className="jp-card" style={{ padding: '20px 24px' }}>
        <div className="jp-serif" style={{ fontSize: 22, fontWeight: 700, color: 'var(--jp-ink)' }}>
          意见反馈
        </div>
        <Text style={{ color: 'var(--jp-ink-2)', fontSize: 13 }}>
          遇到问题或有好建议？告诉我们，帮助广州天气旅行助手变得更好。
        </Text>
      </div>

      <div className="jp-card" style={{ padding: 24 }}>
        {error && (
          <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />
        )}

        <Space direction="vertical" size={6} style={{ width: '100%', marginBottom: 16 }}>
          <Text style={{ color: 'var(--jp-ink)', fontWeight: 600 }}>反馈类型（可选）</Text>
          <Space wrap>
            {PRESET_TAGS.map((t) => (
              <Button
                key={t}
                size="small"
                type={content.startsWith(`【${t}】`) ? 'primary' : 'default'}
                onClick={() =>
                  setContent((prev) =>
                    prev.startsWith('【')
                      ? `【${t}】${prev.replace(/^【.*】/, '')}`
                      : `【${t}】${prev}`,
                  )
                }
              >
                {t}
              </Button>
            ))}
          </Space>
        </Space>

        <Paragraph style={{ color: 'var(--jp-ink)', fontWeight: 600, marginBottom: 6 }}>
          反馈内容 <Text type="danger">*</Text>
        </Paragraph>
        <TextArea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={6}
          maxLength={1000}
          showCount
          placeholder="请描述您遇到的问题或建议……"
          style={{ marginBottom: 20 }}
        />

        <Paragraph style={{ color: 'var(--jp-ink)', fontWeight: 600, marginBottom: 6 }}>
          联系方式（可选）
        </Paragraph>
        <Input
          value={contact}
          onChange={(e) => setContact(e.target.value)}
          prefix={<MailOutlined />}
          placeholder="手机号 / 邮箱 / 微信，方便我们回复您"
          style={{ marginBottom: 24 }}
        />

        <Space>
          <Button
            type="primary"
            icon={<SendOutlined />}
            loading={submitting}
            onClick={handleSubmit}
          >
            提交反馈
          </Button>
          <Button onClick={() => { setContent(''); setContact('') }}>清空</Button>
        </Space>
      </div>

      <Alert
        type="info"
        icon={<BulbOutlined />}
        message="提示：反馈内容仅用于产品优化，我们不会对外公开您的个人信息。"
        showIcon
      />
    </Space>
  )
}
