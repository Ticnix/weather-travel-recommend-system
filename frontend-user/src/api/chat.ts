import http from './http'
import { getToken } from './auth'

export interface StreamEvent {
  type: 'intent' | 'token' | 'done' | string
  intent?: string
  content?: string
}

/**
 * 发起 SSE 流式对话，逐事件回调。
 *
 * ⚠️ 这里必须用原生 fetch（axios 不适合逐块读取流），
 * 但因此**需要手动带上 Authorization** —— axios 的请求拦截器管不到 fetch。
 * 此前漏了这一步，导致已登录用户被后端当成匿名：
 * 对话不落库、左侧历史里自然也看不到。
 */
export async function streamChat(
  message: string,
  conversationId: string,
  onEvent: (evt: StreamEvent) => void,
): Promise<void> {
  const token = getToken()
  const resp = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, conversation_id: conversationId }),
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
        onEvent(JSON.parse(payload) as StreamEvent)
      } catch {
        // 忽略无法解析的行
      }
    }
  }
}

// 历史会话（仅登录用户持久化）
export interface ConversationItem {
  conversation_id: string
  title: string
  count: number
  last_at: string | null
}

export interface ConversationMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string | null
}

interface ConversationListData {
  items: ConversationItem[]
  total: number
}

interface ConversationMessagesData {
  conversation_id: string
  items: ConversationMessage[]
  total: number
}

// 会话列表（按最后活跃时间倒序）
export async function listConversations(): Promise<ConversationItem[]> {
  const res = (await http.get('/chat/conversations')) as unknown as ConversationListData
  return res?.items ?? []
}

// 读取某个会话的全部消息（时间正序），用于回放
export async function getConversationMessages(id: string): Promise<ConversationMessage[]> {
  const res = (await http.get(
    `/chat/conversations/${id}`,
  )) as unknown as ConversationMessagesData
  return res?.items ?? []
}

export async function deleteConversation(id: string): Promise<{ deleted: number }> {
  return http.delete(`/chat/conversations/${id}`)
}
