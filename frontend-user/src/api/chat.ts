import http from './http'

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
