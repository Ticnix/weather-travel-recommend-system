import { Avatar, Button, Input, Space, Typography, Spin } from 'antd'
import { RobotOutlined, SendOutlined, UserOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

const { Paragraph } = Typography
const { TextArea } = Input

interface Message {
  role: 'user' | 'assistant'
  content: string
  intent?: string
  streaming?: boolean
}

const SUGGESTIONS = [
  '广州今天天气怎么样',
  '明天爬山穿什么',
  '从广州南站去广州塔怎么走',
  '明天去广州塔玩，适合穿什么，怎么去最方便',
]

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [searchParams] = useSearchParams()
  const listRef = useRef<HTMLDivElement>(null)
  const conversationRef = useRef<string | null>(null)

  useEffect(() => {
    const topic = searchParams.get('topic')
    if (topic) {
      const map: Record<string, string> = {
        outfit: '明天去广州塔玩，适合穿什么',
        travel: '从广州南站去广州塔怎么走',
        itinerary: '明天有什么安排，要注意什么',
      }
      if (map[topic]) setInput(map[topic])
    }
  }, [searchParams])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const send = async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || sending) return

    setInput('')
    setSending(true)
    setMessages((prev) => [
      ...prev,
      { role: 'user', content },
      { role: 'assistant', content: '', streaming: true },
    ])

    try {
      const resp = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, conversation_id: conversationRef.current }),
      })

      if (!resp.ok || !resp.body) throw new Error('流式请求失败')

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          const payload = trimmed.slice(5).trim()
          if (!payload) continue
          try {
            const evt = JSON.parse(payload)
            if (evt.type === 'intent') {
              setMessages((prev) => {
                const next = [...prev]
                const last = next[next.length - 1]
                if (last?.role === 'assistant') last.intent = evt.intent
                return next
              })
            } else if (evt.type === 'token') {
              setMessages((prev) => {
                const next = [...prev]
                const last = next[next.length - 1]
                if (last?.role === 'assistant') last.content += evt.content
                return next
              })
            }
          } catch {
            // 忽略无法解析的行
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last?.role === 'assistant') last.content = '抱歉，AI 服务暂时不可用，请稍后重试。'
        return next
      })
    } finally {
      setSending(false)
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1]
        if (last?.role === 'assistant') last.streaming = false
        return next
      })
    }
  }

  return (
    <div
      className="jp-card"
      style={{
        height: 'calc(100vh - 170px)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* 消息列表 */}
      <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', marginTop: 80 }}>
            <span style={{ fontSize: 52 }}>🌤️</span>
            <div className="jp-serif" style={{ fontSize: 20, marginTop: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
              和 AI 助手聊聊天气、穿搭、出行吧
            </div>
            <div style={{ marginTop: 24 }}>
              <Space wrap style={{ justifyContent: 'center' }}>
                {SUGGESTIONS.map((s) => (
                  <Button
                    key={s}
                    size="small"
                    onClick={() => send(s)}
                    style={{ borderColor: 'var(--jp-border-strong)', color: 'var(--jp-indigo)' }}
                  >
                    {s}
                  </Button>
                ))}
              </Space>
            </div>
          </div>
        ) : (
          <Space direction="vertical" size={20} style={{ width: '100%' }}>
            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <Space align="start" size={10} style={{ maxWidth: '80%' }}>
                  {msg.role === 'assistant' && (
                    <Avatar
                      icon={<RobotOutlined />}
                      style={{ background: 'var(--jp-bg-2)', color: 'var(--jp-indigo)', border: '1px solid var(--jp-border-strong)' }}
                    />
                  )}
                  <div>
                    {msg.role === 'assistant' && msg.intent && (
                      <span className="jp-chip" style={{ marginBottom: 4, color: 'var(--jp-moss)', borderColor: 'var(--jp-moss)' }}>
                        意图: {msg.intent}
                      </span>
                    )}
                    <div
                      style={{
                        background:
                          msg.role === 'user'
                            ? 'var(--jp-indigo)'
                            : 'var(--jp-panel-2)',
                        border:
                          msg.role === 'user'
                            ? '1px solid var(--jp-indigo)'
                            : '1px solid var(--jp-border)',
                        color: msg.role === 'user' ? '#fffdf9' : 'var(--jp-ink)',
                        padding: '10px 14px',
                        borderRadius: 14,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        boxShadow: 'var(--jp-shadow-sm)',
                      }}
                    >
                      {msg.content}
                      {msg.streaming && msg.content === '' && <Spin size="small" />}
                    </div>
                  </div>
                  {msg.role === 'user' && (
                    <Avatar
                      icon={<UserOutlined />}
                      style={{ background: 'var(--jp-sakura)', color: '#fffdf9', border: '1px solid var(--jp-sakura)' }}
                    />
                  )}
                </Space>
              </div>
            ))}
          </Space>
        )}
      </div>

      {/* 输入区 */}
      <div style={{ borderTop: '1px solid var(--jp-border)', padding: '16px 24px' }}>
        <Space.Compact style={{ width: '100%' }}>
          <TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入你的问题，如：明天去广州塔穿什么？"
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            disabled={sending}
            style={{ background: 'var(--jp-panel)' }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={() => send()}
            loading={sending}
            style={{ height: 'auto' }}
          >
            发送
          </Button>
        </Space.Compact>
        <Paragraph style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--jp-ink-3)' }}>
          <ThunderboltOutlined style={{ color: 'var(--jp-amber)' }} /> 支持天气查询、穿搭推荐、出行规划
          · Enter 发送 · Shift+Enter 换行
        </Paragraph>
      </div>
    </div>
  )
}
