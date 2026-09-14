import http from './http'

// 资讯分类：news 普通资讯 / notice 官方公告 / alert 气象预警（采集自中央气象台）
export type NewsCategory = 'news' | 'notice' | 'alert'

export interface NewsItem {
  id: number
  title: string
  content: string
  cover_url: string | null
  category: NewsCategory
  author: string | null
  is_top: boolean
  is_published: boolean
  view_count: number
  created_at: string
  updated_at: string
}

export interface NewsListResult {
  items: NewsItem[]
  total: number
  page: number
  page_size: number
}

export interface NewsListParams {
  page?: number
  page_size?: number
  category?: NewsCategory | null
  keyword?: string
  published_only?: boolean
}

// 资讯列表（公开，只取已发布）
export async function listNews(params: NewsListParams = {}): Promise<NewsListResult> {
  return http.get('/news', {
    params: {
      page: params.page ?? 1,
      page_size: params.page_size ?? 12,
      category: params.category ?? undefined,
      keyword: params.keyword ?? undefined,
      published_only: params.published_only ?? true,
    },
  })
}

// 资讯详情（公开，阅读量+1）
export async function getNews(id: number): Promise<NewsItem> {
  return http.get(`/news/${id}`)
}
