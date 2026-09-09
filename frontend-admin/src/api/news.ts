import http from './http'

export interface NewsItem {
  id: number
  title: string
  content: string
  cover_url: string | null
  category: 'news' | 'notice'
  author: string | null
  is_top: boolean
  is_published: boolean
  view_count: number
  created_at: string
  updated_at: string
}

export interface NewsQuery {
  page?: number
  page_size?: number
  category?: 'news' | 'notice' | ''
  keyword?: string
  published?: '' | 'true' | 'false'
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// 资讯/公告列表（含未发布）
export function listNews(params: NewsQuery = {}): Promise<PageResult<NewsItem>> {
  return http.get('/news', {
    params: {
      page: 1,
      page_size: 20,
      published_only: false,
      ...params,
    },
  })
}

export function createNews(payload: Partial<NewsItem>): Promise<NewsItem> {
  return http.post('/news', payload)
}

export function updateNews(id: number, payload: Partial<NewsItem>): Promise<NewsItem> {
  return http.put(`/news/${id}`, payload)
}

export function deleteNews(id: number): Promise<NewsItem> {
  return http.delete(`/news/${id}`)
}
