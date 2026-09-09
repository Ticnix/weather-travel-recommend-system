import http from './http'

export interface FeedbackItem {
  id: number
  content: string
  contact: string | null
  status: 'pending' | 'processing' | 'resolved' | 'closed'
  reply: string | null
  reply_at: string | null
  user_id: number | null
  username: string | null
  created_at: string
  updated_at: string
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export function listFeedback(page = 1, page_size = 20, status?: string): Promise<PageResult<FeedbackItem>> {
  return http.get('/feedback', { params: { page, page_size, status_filter: status || undefined } })
}

export function updateFeedback(id: number, payload: { status?: string; reply?: string }): Promise<FeedbackItem> {
  return http.put(`/feedback/${id}`, payload)
}
