import { Avatar, Button, Input, Popconfirm, Space, Spin, Typography, message } from 'antd'
import {
  DeleteOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import MarkdownPreview from '@uiw/react-markdown-preview'
import '@uiw/react-markdown-preview/markdown.css'
import { isLoggedIn } from '../api/auth'
import {
  deleteConversation,
  getConversationMessages,
  listConversations,
  streamChat,
  type ConversationItem,
} from '../api/chat'

const { Paragraph, Text } = Typography
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

// 前端生成会话 id（与后端 uuid4().hex[:16] 同一格式）。
// 原因：SSE 流不返回 conversation_id，前端自己生成才能立刻在侧栏定位新会话。
function newConvId(): string {
  return Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [searchParams] = useSearchParams()
  const listRef = useRef<HTMLDivElement>(null)

  // 历史会话（仅登录用户）
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  const loggedIn = isLoggedIn()

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

  const loadConversations = useCallback(async () => {
    if (!loggedIn) return
    try {
      setConversations(await listConversations())
    } catch {
      /* 失败提示已由 http 拦截器统一处理 */
    }
  }, [loggedIn])

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  // 打开某个历史会话：回放全部消息
  const openConversation = async (id: string) => {
    if (sending) return
    setActiveConvId(id)
    try {
      const items = await getConversationMessages(id)
      setMessages(items.map((m) => ({ role: m.role, content: m.content })))
    } catch {
      setMessages([])
    }
  }

  // 新对话：只清空当前视图，不删除历史
  const startNewChat = () => {
    setActiveConvId(null)
    setMessages([])
    setInput('')
  }

  const handleDeleteConversation = async (id: string) => {
    try {
      await deleteConversation(id)
      message.success('已删除')
      if (activeConvId === id) startNewChat()
      await loadConversations()
    } catch {
      /* 拦截器已提示 */
    }
  }

  const send = async (text?: string) => {
    const content = (text ?? input).trim()
    if (!content || sending) return

    // 没有当前会话就开一个新的（id 由前端生成，便于立刻高亮）
    const convId = activeConvId ?? newConvId()
    if (!activeConvId) setActiveConvId(convId)

    setInput('')
    setSending(true)
    setMessages((prev) => [
      ...prev,
      { role: 'user', content },
      { role: 'assistant', content: '', streaming: true },
    ])

    try {
      // 走 api 层封装：内部会带上 Authorization（裸 fetch 会绕过 axios 拦截器，
      // 之前就是这里漏了 token，导致登录用户被当成匿名、对话不落库）
      await streamChat(content, convId, (evt) => {
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
            if (last?.role === 'assistant') last.content += evt.content ?? ''
            return next
          })
        }
      })
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
      // 登录用户：刷新会话列表（标题 / 时间 / 条数）
      if (loggedIn) loadConversations()
    }
  }

  return (
    <div
      className="jp-card"
      style={{
        height: 'calc(100vh - 170px)',
        display: 'flex',
        overflow: 'hidden',
      }}
    >
      {/* 历史会话侧栏（仅登录用户可见，匿名对话不持久化） */}
      {loggedIn && (
        <div
          style={{
            width: 234,
            flexShrink: 0,
            borderRight: '1px solid var(--jp-border)',
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--jp-panel)',
          }}
        >
          <div style={{ padding: 12 }}>
            <Button block type="primary" icon={<PlusOutlined />} onClick={startNewChat}>
              新对话
            </Button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 10px 12px' }}>
            {conversations.length === 0 ? (
              <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>
                还没有历史对话，聊几句就会出现在这里
              </Text>
            ) : (
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                {conversations.map((cv) => {
                  const active = activeConvId === cv.conversation_id
                  return (
                    <div
                      key={cv.conversation_id}
                      onClick={() => openConversation(cv.conversation_id)}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 8,
                        cursor: 'pointer',
                        display: 'flex',
                        gap: 6,
                        alignItems: 'center',
                        background: active ? 'var(--jp-panel-2)' : 'transparent',
                        border: `1px solid ${active ? 'var(--jp-border-strong)' : 'transparent'}`,
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            fontSize: 13,
                            color: 'var(--jp-ink)',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {cv.title || '新对话'}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--jp-ink-3)' }}>
                          {cv.last_at ? `${cv.last_at.slice(5, 16).replace('T', ' ')} · ${cv.count} 条` : ''}
                        </div>
                      </div>
                      <Popconfirm
                        title="删除该会话？"
                        onConfirm={() => handleDeleteConversation(cv.conversation_id)}
                      >
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Popconfirm>
                    </div>
                  )
                })}
              </Space>
            )}
          </div>
        </div>
      )}

      {/* 右侧：消息区 + 输入区 */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* 消息列表 */}
        <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
          {messages.length === 0 ? (
            <div style={{ textAlign: 'center', marginTop: 70 }}>
              <span style={{ fontSize: 52 }}>🌤️</span>
              <div
                className="jp-serif"
                style={{ fontSize: 20, marginTop: 16, fontWeight: 600, color: 'var(--jp-ink)' }}
              >
                和 AI 助手聊聊天气、穿搭、出行吧
              </div>
              {loggedIn ? (
                <div style={{ marginTop: 6, fontSize: 12, color: 'var(--jp-ink-3)' }}>
                  对话会自动保存，可在左侧查看历史记录
                </div>
              ) : (
                <div style={{ marginTop: 6, fontSize: 12, color: 'var(--jp-ink-3)' }}>
                  当前未登录，对话不会保存；登录后可查看历史记录
                </div>
              )}
              <div style={{ marginTop: 22 }}>
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
                        style={{
                          background: 'var(--jp-bg-2)',
                          color: 'var(--jp-indigo)',
                          border: '1px solid var(--jp-border-strong)',
                        }}
                      />
                    )}
                    <div>
                      {msg.role === 'assistant' && msg.intent && (
                        <span
                          className="jp-chip"
                          style={{ marginBottom: 4, color: 'var(--jp-moss)', borderColor: 'var(--jp-moss)' }}
                        >
                          意图: {msg.intent}
                        </span>
                      )}
                      <div
                        style={{
                          background:
                            msg.role === 'user' ? 'var(--jp-indigo)' : 'var(--jp-panel-2)',
                          border:
                            msg.role === 'user'
                              ? '1px solid var(--jp-indigo)'
                              : '1px solid var(--jp-border)',
                          color: msg.role === 'user' ? '#fffdf9' : 'var(--jp-ink)',
                          padding: '10px 14px',
                          borderRadius: 14,
                          whiteSpace: msg.role === 'user' ? 'pre-wrap' : undefined,
                          wordBreak: 'break-word',
                          boxShadow: 'var(--jp-shadow-sm)',
                        }}
                      >
                        {msg.role === 'assistant' ? (
                          msg.content ? (
                            /* AI 输出的是 Markdown：需渲染成排版。
                               此前直接当纯文本输出，导致 ** 与 - 等标记裸显 */
                            <div className="jp-chat-md" data-color-mode="light">
                              <MarkdownPreview
                                source={msg.content}
                                style={{
                                  background: 'transparent',
                                  color: 'var(--jp-ink)',
                                  fontSize: 14,
                                  lineHeight: 1.75,
                                }}
                              />
                            </div>
                          ) : (
                            <Spin size="small" />
                          )
                        ) : (
                          msg.content
                        )}
                      </div>
                    </div>
                    {msg.role === 'user' && (
                      <Avatar
                        icon={<UserOutlined />}
                        style={{
                          background: 'var(--jp-sakura)',
                          color: '#fffdf9',
                          border: '1px solid var(--jp-sakura)',
                        }}
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
    </div>
  )
}
