import { Avatar, Button, Drawer, Input, Popconfirm, Popover, Space, Tag, Tooltip, Typography, message } from 'antd'
import {
  AudioOutlined,
  DeleteOutlined,
  FileTextOutlined,
  HistoryOutlined,
  PictureOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import MarkdownPreview from '@uiw/react-markdown-preview'
import '@uiw/react-markdown-preview/markdown.css'
import { isLoggedIn } from '../api/auth'
import {
  deleteConversation,
  getConversationMessages,
  listConversations,
  streamChat,
  uploadAttachment,
  type AttachmentMeta,
  type ConversationItem,
} from '../api/chat'
import LoadingState from '../components/LoadingState'
import { useIsMobile } from '../utils/useIsMobile'
import { MAX_UPLOAD_BYTES, formatFileSize, prepareUpload } from '../utils/prepareUpload'
import { apiErrorText } from '../utils/apiError'

const { Paragraph, Text } = Typography
const { TextArea } = Input

interface Message {
  role: 'user' | 'assistant'
  content: string
  intent?: string
  streaming?: boolean
  /** 这条用户消息带了哪些附件（只用于展示，真正的解析结果在后端） */
  attachments?: string[]
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
  const isMobile = useIsMobile()

  // 手机上的历史会话收进抽屉：桌面那个 234px 常驻侧栏在手机上会把消息区
  // 挤到只剩几十像素宽——每个字被迫单独一行，就是用户看到的"排版全乱了"。
  const [historyOpen, setHistoryOpen] = useState(false)

  // 聊天区高度要**量**出来，不能写死：手机上浏览器工具栏、底部导航、Home 条
  // 安全区都会吃掉高度，写死 calc(100vh - N) 时输入框会被顶到屏幕外。
  const chatBoxRef = useRef<HTMLDivElement>(null)
  const [chatHeight, setChatHeight] = useState<number | undefined>(undefined)

  useLayoutEffect(() => {
    if (!isMobile) {
      setChatHeight(undefined)
      return
    }
    const measure = () => {
      const el = chatBoxRef.current
      if (!el) return
      const top = el.getBoundingClientRect().top + window.scrollY
      const nav = document.querySelector('.jp-bottom-nav')?.getBoundingClientRect().height ?? 0
      // innerHeight（而非 100vh）已经排除了 Safari 的工具栏，量出来才准
      setChatHeight(Math.max(320, Math.round(window.innerHeight - top - nav - 10)))
    }
    measure()
    // 顶部提示条（安装引导）显示/隐藏会改变卡片位置，body 尺寸一变就重新量
    const observer = new ResizeObserver(measure)
    observer.observe(document.body)
    window.addEventListener('resize', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [isMobile])

  /**
   * 只改最后一条 AI 消息，且**必须返回新对象**。
   *
   * 之前是在 updater 里直接改旧对象（`last.content += evt.content`）。
   * updater 必须是纯函数：React 会先跑一遍算 eager state、渲染时再跑一遍，
   * 于是每个 token 被追加两次——AI 的回答就成了"重重复复的字"。
   * 改成新建对象后，同样的输入算多少次结果都一样。
   */
  const patchLastAssistant = useCallback((patch: (msg: Message) => Message) => {
    setMessages((prev) => {
      const lastIndex = prev.length - 1
      const last = prev[lastIndex]
      if (!last || last.role !== 'assistant') return prev
      const next = prev.slice()
      next[lastIndex] = patch(last)
      return next
    })
  }, [])

  // 历史会话（仅登录用户）
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [activeConvId, setActiveConvId] = useState<string | null>(null)
  // 历史会话首次加载 / 加载失败：原本两种情况都表现为"还没有历史对话"，
  // 用户会以为自己之前聊的全丢了
  const [convLoading, setConvLoading] = useState(true)
  const [convFailed, setConvFailed] = useState(false)
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
    if (!loggedIn) {
      setConvLoading(false)
      return
    }
    setConvFailed(false)
    try {
      setConversations(await listConversations())
    } catch {
      setConversations([])
      setConvFailed(true)
    } finally {
      setConvLoading(false)
    }
  }, [loggedIn])

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  // ===== 多模态附件（图片 / 语音 / 文件）=====
  const [attachments, setAttachments] = useState<AttachmentMeta[]>([])
  const [uploading, setUploading] = useState(false)
  const [recording, setRecording] = useState(false)
  // 「+」号展开的附件菜单（图片 / 文件 / 语音）
  const [attachMenuOpen, setAttachMenuOpen] = useState(false)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const acceptAttachment = useCallback(async (file: File) => {
    const limit = formatFileSize(MAX_UPLOAD_BYTES)

    // 图片有压缩兜底，其它类型没有：**先本地判大小**，点选的那一刻就告诉用户，
    // 不用等传完一轮才收到 400（手机上上行慢，这个差别很明显）
    if (!file.type.startsWith('image/') && file.size > MAX_UPLOAD_BYTES) {
      message.error(
        `「${file.name}」${formatFileSize(file.size)}，超过单个附件 ${limit} 上限，` +
          '请压缩或拆分后再传',
        8,
      )
      return
    }

    setUploading(true)
    try {
      // 图片先在前端压：手机原图/微信原图常超 8MB 上限，上传阶段就会 400
      const { file: prepared, note } = await prepareUpload(file)
      if (note) message.info(note)
      // 压缩后仍超限（极端大图 / 压缩失败）：也说清楚，别浪费一次上传
      if (prepared.size > MAX_UPLOAD_BYTES) {
        message.error(
          `「${file.name}」压缩后仍有 ${formatFileSize(prepared.size)}，超过 ${limit} 上限，` +
            '请换一张更小的图或先自行裁剪',
          8,
        )
        return
      }
      const meta = await uploadAttachment(prepared)
      // 与后端上限一致：最多 5 个，超出时挤掉最早那个（比直接拒绝更符合预期）
      setAttachments((prev) => (prev.length >= 5 ? [...prev.slice(1), meta] : [...prev, meta]))
      message.success(meta.preview || '附件已解析')
    } catch (err) {
      // **必须明确报出来**：只靠全局拦截器时，一次上传失败很容易被漏看，
      // 用户会以为"附件已经带上了"，接着收到一句"没看到图"的回答（实测踩过）。
      message.error(`「${file.name}」上传失败：${apiErrorText(err)}`, 8)
    } finally {
      setUploading(false)
    }
  }, [])

  const onPickFiles = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    event.target.value = '' // 置空才能连续选同一个文件
    // 串行上传：并行时返回顺序不定，预览会乱跳
    for (const file of files) await acceptAttachment(file)
  }

  const toggleRecord = async () => {
    if (recording) {
      recorderRef.current?.stop()
      return
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      message.warning('当前环境不支持录音（需要 HTTPS，且浏览器要支持 MediaRecorder）')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop())
        setRecording(false)
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' })
        // 太短的录音多半是误触，上传也只会换回"没有识别到语音"
        if (blob.size < 1000) {
          message.info('录音太短，没有上传')
          return
        }
        await acceptAttachment(
          new File([blob], `voice-${Date.now()}.webm`, { type: blob.type || 'audio/webm' }),
        )
      }
      recorder.start()
      recorderRef.current = recorder
      setRecording(true)
      message.info('正在录音，再点一次麦克风结束并转写')
    } catch {
      message.warning('没有拿到麦克风权限，无法录音')
    }
  }

  // 打开某个历史会话：回放全部消息
  const openConversation = async (id: string) => {
    if (sending) return
    setHistoryOpen(false) // 手机上是从抽屉里点的，选完要把抽屉收回去
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
    const hasAttachments = attachments.length > 0
    // 只发附件、一个字都不写也要能发（用户就是"把这个文件给你看"，
    // 逼他打字才给发是最容易被骂的设计）。
    // 但上传/解析还没完成时仍然拦住：否则会发出一个 id 还没拿到的附件。
    if ((!content && !hasAttachments) || sending || uploading) return

    // 没有当前会话就开一个新的（id 由前端生成，便于立刻高亮）
    const convId = activeConvId ?? newConvId()
    if (!activeConvId) setActiveConvId(convId)

    const attachmentIds = attachments.map((a) => a.id)
    const attachmentNames = attachments.map((a) => a.name)

    setInput('')
    setAttachments([])
    setSending(true)
    setMessages((prev) => [
      ...prev,
      { role: 'user', content, attachments: attachmentNames },
      { role: 'assistant', content: '', streaming: true },
    ])

    try {
      // 走 api 层封装：内部会带上 Authorization（裸 fetch 会绕过 axios 拦截器，
      // 之前就是这里漏了 token，导致登录用户被当成匿名、对话不落库）
      await streamChat(content, convId, (evt) => {
        if (evt.type === 'intent') {
          patchLastAssistant((msg) => ({ ...msg, intent: evt.intent }))
        } else if (evt.type === 'token') {
          patchLastAssistant((msg) => ({ ...msg, content: msg.content + (evt.content ?? '') }))
        }
      }, attachmentIds)
    } catch {
      patchLastAssistant(() => ({
        role: 'assistant',
        content: '抱歉，AI 服务暂时不可用，请稍后重试。',
      }))
    } finally {
      setSending(false)
      patchLastAssistant((msg) => ({ ...msg, streaming: false }))
      // 登录用户：刷新会话列表（标题 / 时间 / 条数）
      if (loggedIn) loadConversations()
    }
  }

  const activeTitle =
    conversations.find((cv) => cv.conversation_id === activeConvId)?.title ?? null

  // 历史会话面板：桌面常驻左侧、手机放进抽屉——同一份 JSX，两种容器
  const historyPanel = (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        background: 'var(--jp-panel)',
      }}
    >
      <div style={{ padding: 12 }}>
        <Button block type="primary" icon={<PlusOutlined />} onClick={startNewChat}>
          新对话
        </Button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 10px 12px' }}>
            {conversations.length === 0 && convLoading ? (
              <LoadingState compact text="正在加载历史对话…" />
            ) : conversations.length === 0 && convFailed ? (
              <Text style={{ fontSize: 12, color: 'var(--jp-vermilion)' }}>
                历史对话没能加载出来，
                <Button
                  type="link"
                  size="small"
                  style={{ padding: 0 }}
                  onClick={() => void loadConversations()}
                >
                  点此重试
                </Button>
              </Text>
            ) : conversations.length === 0 ? (
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
  )

  return (
    <div
      ref={chatBoxRef}
      className="jp-card"
      style={{
        // 手机上按实测可用高度撑满（浏览器工具栏/底部导航/安全区都会变），
        // 桌面沿用固定值
        height: isMobile ? (chatHeight ?? 'calc(100dvh - 210px)') : 'calc(100vh - 170px)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* 手机：历史会话入口。宽度全部留给消息区，不再常驻 234px 侧栏 */}
      {isMobile && loggedIn && (
        <div
          style={{
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 10px',
            borderBottom: '1px solid var(--jp-border)',
          }}
        >
          <Button size="small" icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)}>
            历史对话
          </Button>
          <div
            style={{
              flex: 1,
              minWidth: 0,
              fontSize: 12,
              color: 'var(--jp-ink-3)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {activeTitle ?? (conversations.length ? `共 ${conversations.length} 段` : '还没有历史对话')}
          </div>
        </div>
      )}

      {/* 手机：历史会话抽屉（选完自动收起，见 openConversation） */}
      {isMobile && loggedIn && (
        <Drawer
          title="历史对话"
          placement="left"
          size={272}
          open={historyOpen}
          onClose={() => setHistoryOpen(false)}
          styles={{ body: { padding: 0 } }}
        >
          {historyPanel}
        </Drawer>
      )}

      <div style={{ flex: 1, minHeight: 0, display: 'flex', overflow: 'hidden' }}>
        {/* 桌面：历史会话常驻左侧（仅登录用户，匿名对话不持久化） */}
        {!isMobile && loggedIn && (
          <div
            style={{
              width: 234,
              flexShrink: 0,
              borderRight: '1px solid var(--jp-border)',
            }}
          >
            {historyPanel}
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
        <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: isMobile ? '14px 12px' : '24px' }}>
          {messages.length === 0 ? (
            <div style={{ textAlign: 'center', marginTop: isMobile ? 34 : 70 }}>
              <span style={{ fontSize: isMobile ? 40 : 52 }}>🌤️</span>
              <div
                className="jp-serif"
                style={{
                  fontSize: isMobile ? 17 : 20,
                  marginTop: isMobile ? 10 : 16,
                  fontWeight: 600,
                  color: 'var(--jp-ink)',
                }}
              >
                和 AI 助手聊聊天气、穿搭、出行吧
              </div>
              {loggedIn ? (
                <div style={{ marginTop: 6, fontSize: 12, color: 'var(--jp-ink-3)' }}>
                  {isMobile
                    ? '对话会自动保存，点上方「历史对话」可查看'
                    : '对话会自动保存，可在左侧查看历史记录'}
                </div>
              ) : (
                <div style={{ marginTop: 6, fontSize: 12, color: 'var(--jp-ink-3)' }}>
                  当前未登录，对话不会保存；登录后可查看历史记录
                </div>
              )}
              <div style={{ marginTop: isMobile ? 16 : 22 }}>
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
            <Space direction="vertical" size={isMobile ? 14 : 20} style={{ width: '100%' }}>
              {messages.map((msg, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  }}
                >
                  {/* 手机上气泡几乎占满整行：屏幕本来就窄，再留 20% 会让长句频繁换行 */}
                  <Space align="start" size={isMobile ? 8 : 10} style={{ maxWidth: isMobile ? '100%' : '80%' }}>
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
                          padding: isMobile ? '9px 11px' : '10px 14px',
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
                                  fontSize: isMobile ? 13.5 : 14,
                                  lineHeight: 1.75,
                                }}
                              />
                            </div>
                          ) : (
                            /* 大模型回答要等几秒到十几秒：只转圈不说在做什么，
                               用户会以为卡住而反复点发送 */
                            <LoadingState
                              compact
                              text="AI 正在思考…"
                              hint="正在结合实时天气与知识库生成回答，通常 5~15 秒，请稍等"
                            />
                          )
                        ) : (
                          <>
                            {/* 只发附件时气泡会空着，标一下"仅附件"更清楚 */}
                            {msg.content || (msg.attachments?.length ? '（仅附件）' : '')}
                            {/* 把"带过什么附件"标在气泡里：多轮对话里不标，用户回头看不明白
                                自己那句话在说什么（"这张图"到底指哪张） */}
                            {msg.attachments && msg.attachments.length > 0 && (
                              <div style={{ marginTop: 6, fontSize: 12, opacity: 0.85 }}>
                                {msg.attachments.map((name) => (
                                  <span key={name} style={{ marginRight: 8 }}>
                                    📎 {name}
                                  </span>
                                ))}
                              </div>
                            )}
                          </>
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
        <div
          style={{
            flexShrink: 0,
            borderTop: '1px solid var(--jp-border)',
            padding: isMobile ? '10px 12px' : '16px 24px',
          }}
        >
          {/* 已上传的附件：上传时就解析完了，这里给出结果摘要，
              让用户能确认"它真的读到了"，而不是发出去才知道没读到 */}
          {attachments.length > 0 && (
            <Space wrap size={6} style={{ marginBottom: 8 }}>
              {attachments.map((item) => (
                <Tag
                  key={item.id}
                  closable
                  onClose={() => setAttachments((prev) => prev.filter((a) => a.id !== item.id))}
                  color={item.kind === 'image' ? 'cyan' : item.kind === 'audio' ? 'purple' : 'blue'}
                  icon={
                    item.kind === 'image' ? (
                      <PictureOutlined />
                    ) : item.kind === 'audio' ? (
                      <AudioOutlined />
                    ) : (
                      <FileTextOutlined />
                    )
                  }
                >
                  <Tooltip title={item.preview}>
                    <span>
                      {item.name}
                      {item.kind !== 'image' && item.chars ? ` · ${item.chars} 字` : ''}
                    </span>
                  </Tooltip>
                </Tag>
              ))}
            </Space>
          )}

          {/* 附件工具组 · 输入框 · 发送：三段**分开**并留出间距。
              原来用 Space.Compact 把三个图标按钮和输入框焊成一整条，
              图标紧贴输入框左边缘、占位文字又贴着图标，手机上看着挤成一团。 */}
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-end',
              gap: isMobile ? 8 : 12,
            }}
          >
            {/* 附件入口收成一个「+」，点了才展开三项。
                三个图标常驻会把输入区挤得很乱（手机上尤其明显）；
                录音时则**直接显示"停止"**——录音是正在进行中的状态，
                藏进菜单里用户会找不到怎么停。 */}
            {recording ? (
              <Button
                danger
                size={isMobile ? 'small' : 'middle'}
                icon={<AudioOutlined />}
                onClick={() => void toggleRecord()}
                style={{ flexShrink: 0 }}
              >
                停止
              </Button>
            ) : (
              <Popover
                open={attachMenuOpen}
                onOpenChange={setAttachMenuOpen}
                trigger="click"
                placement="topLeft"
                arrow={false}
                content={
                  // 宽度/内边距加在自己的容器上：Popover 的 styles 键名各版本不同
                  // （v6 里没有 body，只有 content/root/container），写死在这里最稳
                  <div style={{ padding: 4, width: isMobile ? 216 : 244 }}>
                    {[
                      {
                        key: 'image',
                        icon: <PictureOutlined />,
                        title: '图片',
                        desc: `识别画面内容，超过 ${formatFileSize(MAX_UPLOAD_BYTES)} 自动压缩`,
                        run: () => imageInputRef.current?.click(),
                      },
                      {
                        key: 'file',
                        icon: <FileTextOutlined />,
                        title: '文件',
                        desc: `PDF / Word / Excel，单个 ≤ ${formatFileSize(MAX_UPLOAD_BYTES)}`,
                        run: () => fileInputRef.current?.click(),
                      },
                      {
                        key: 'audio',
                        icon: <AudioOutlined />,
                        title: '语音',
                        desc: '录一段话，自动转成文字',
                        run: () => void toggleRecord(),
                      },
                    ].map((item) => (
                      <button
                        key={item.key}
                        type="button"
                        className="jp-attach-item"
                        onClick={() => {
                          setAttachMenuOpen(false)
                          item.run()
                        }}
                      >
                        <span style={{ fontSize: 18, color: '#3b5b8c', lineHeight: 1 }}>
                          {item.icon}
                        </span>
                        <span style={{ minWidth: 0 }}>
                          <span
                            style={{
                              display: 'block',
                              fontSize: 13,
                              fontWeight: 600,
                              color: 'var(--jp-ink)',
                            }}
                          >
                            {item.title}
                          </span>
                          <span
                            style={{
                              display: 'block',
                              fontSize: 11,
                              lineHeight: 1.4,
                              color: 'var(--jp-ink-3)',
                            }}
                          >
                            {item.desc}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                }
              >
                <Button
                  size={isMobile ? 'small' : 'middle'}
                  icon={<PlusOutlined />}
                  loading={uploading}
                  style={{ flexShrink: 0 }}
                  aria-label="添加图片 / 文件 / 语音"
                />
              </Popover>
            )}

            <TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              // 手机上占位文案会折成两行、把输入框撑高，只留短语。
              // 已有附件时改为提示"可以直接发"，否则用户会以为必须写字。
              placeholder={
                attachments.length > 0
                  ? '可补充说明，留空也能直接发送'
                  : isMobile
                    ? '输入你的问题…'
                    : '输入你的问题，如：明天去广州塔穿什么？'
              }
              autoSize={{ minRows: 1, maxRows: 4 }}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              disabled={sending}
              style={{ flex: 1, minWidth: 0, background: 'var(--jp-panel)' }}
            />

            <Button
              type="primary"
              size={isMobile ? 'small' : 'middle'}
              icon={<SendOutlined />}
              onClick={() => send()}
              loading={sending}
              style={{ flexShrink: 0 }}
            >
              {isMobile ? null : '发送'}
            </Button>
          </div>
          {/* 隐藏的文件选择器：用按钮触发，避免原生 input 的丑陋样式 */}
          <input
            ref={imageInputRef}
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => void onPickFiles(e)}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.xlsx,.txt,.md,.csv,.json,.log"
            multiple
            hidden
            onChange={(e) => void onPickFiles(e)}
          />
          {/* 手机上只留键盘操作说明：能力介绍在这一屏属于"多余的文字" */}
          <Paragraph
            style={{ margin: '8px 0 0', fontSize: isMobile ? 11 : 12, color: 'var(--jp-ink-3)' }}
          >
            <ThunderboltOutlined style={{ color: 'var(--jp-amber)' }} />
            {isMobile
              ? ' 可发图片 / 语音 / 文件'
              : ' 支持天气查询、穿搭推荐、出行规划，也可发图片 / 语音 / PDF 等文件 · Enter 发送 · Shift+Enter 换行'}
          </Paragraph>
        </div>
        </div>
      </div>
    </div>
  )
}
