import http from './http'

export interface FeedbackItem {
  id: number
  content: string
  contact: string | null
  status: 'pending' | 'processing' | 'resolved' | 'closed'
  user_id: number | null
  created_at: string
  updated_at: string
}

export interface FeedbackCreatePayload {
  content: string
  contact?: string
}

// 提交反馈（匿名可提交）
export async function createFeedback(payload: FeedbackCreatePayload): Promise<FeedbackItem> {
  return http.post('/feedback', payload)
}

// 我的反馈列表（需登录）
export async function listMyFeedback(page = 1, page_size = 20): Promise<{
  items: FeedbackItem[]
  total: number
  page: number
  page_size: number
}> {
  return http.get('/feedback', { params: { page, page_size } })
}
