/**
 * 我的知识库页面（Day 60）。
 *
 * 后端能力（上传/检索/列表/删除）早已存在，这页只是把它接到用户面前。
 * 入库是**文本**（title+content）：粘贴攻略、笔记即可；
 * .txt/.md 文件在前端读成文本再传（后端不需要管文件存储）。
 */

import { useCallback, useEffect, useState } from 'react'
import {
  Button,
  Empty,
  Input,
  List,
  Popconfirm,
  Space,
  Typography,
  message,
} from 'antd'
import http from '../api/http'
import { isLoggedIn } from '../api/auth'

const { Paragraph, Text, Title } = Typography

interface DocItem {
  title: string
  source?: string | null
  created_at?: string | null
  chunk_count?: number
  [k: string]: unknown
}

interface SearchHit {
  title: string
  content?: string
  similarity?: number
}

export default function MyKnowledge() {
  const [docs, setDocs] = useState<DocItem[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[] | null>(null)
  const [searching, setSearching] = useState(false)

  const load = useCallback(() => {
    http
      .get('/my-knowledge')
      .then((res) => setDocs((res as unknown as { items: DocItem[] })?.items ?? []))
      .catch(() => setFailed(true))
  }, [])

  useEffect(() => {
    if (isLoggedIn()) load()
  }, [load])

  if (!isLoggedIn()) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        <Title level={4} className="jp-serif" style={{ margin: 0 }}>
          我的知识库
        </Title>
        <Paragraph style={{ margin: '8px 0 0', color: 'var(--jp-ink-2)' }}>
          登录后可上传你的出行计划与攻略，AI 回答"我上次计划去哪"这类问题时会**只检索你自己的内容**。
        </Paragraph>
      </div>
    )
  }

  const upload = async () => {
    if (!title.trim() || !content.trim()) {
      message.warning('标题和内容都要填')
      return
    }
    setSaving(true)
    try {
      await http.post('/my-knowledge', { title: title.trim(), content: content.trim() })
      message.success('已入库，AI 之后会检索到它')
      setTitle('')
      setContent('')
      load()
    } catch {
      /* 失败原因由拦截器提示 */
    } finally {
      setSaving(false)
    }
  }

  const pickFile = async (file: File | undefined) => {
    if (!file) return
    if (file.size > 512 * 1024) {
      message.error('文件太大（上限 512KB），请拆分后再传')
      return
    }
    const text = await file.text()
    setContent(text)
    if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, ''))
  }

  const remove = async (docTitle: string) => {
    try {
      await http.delete(`/my-knowledge/${encodeURIComponent(docTitle)}`)
      message.success('已删除')
      load()
    } catch {
      /* 拦截器已提示 */
    }
  }

  const search = async () => {
    if (!query.trim()) return
    setSearching(true)
    try {
      const res = (await http.post('/my-knowledge/search', { query: query.trim(), top_k: 5 })) as {
        items: SearchHit[]
      }
      setHits(res?.items ?? [])
    } catch {
      setHits([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <div className="jp-card" style={{ padding: 20 }}>
        <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
          我的知识库
        </span>
        <Paragraph style={{ marginTop: 6, marginBottom: 14, fontSize: 12.5, color: 'var(--jp-ink-2)' }}>
          上传你的出行计划、攻略、笔记（纯文本即可，.txt/.md 可直接选文件）。
          AI 对话时只在**你自己的内容**里检索，与他人隔离。
        </Paragraph>

        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Input
            placeholder="标题，如：五一厦门攻略"
            value={title}
            maxLength={80}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Input.TextArea
            placeholder="粘贴攻略 / 计划 / 笔记内容…"
            value={content}
            autoSize={{ minRows: 5, maxRows: 12 }}
            onChange={(e) => setContent(e.target.value)}
          />
          <Space wrap>
            <Button type="primary" loading={saving} onClick={() => void upload()}>
              入库
            </Button>
            <label style={{ cursor: 'pointer' }}>
              <input
                type="file"
                accept=".txt,.md,.markdown"
                style={{ display: 'none' }}
                onChange={(e) => void pickFile(e.target.files?.[0])}
              />
              <Button>选择 .txt / .md 文件</Button>
            </label>
          </Space>
        </Space>
      </div>

      <div className="jp-card" style={{ padding: 20 }}>
        <div style={{ marginBottom: 10, display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600, color: 'var(--jp-ink)' }}>
            已入库（{docs?.length ?? 0}）
          </span>
          <Input.Search
            size="small"
            placeholder="试检索：我的行程第二天去哪"
            style={{ maxWidth: 320, marginLeft: 'auto' }}
            value={query}
            enterButton="检索"
            loading={searching}
            onChange={(e) => setQuery(e.target.value)}
            onSearch={() => void search()}
          />
        </div>

        {failed ? (
          <Text type="secondary">列表加载失败，刷新重试。</Text>
        ) : docs === null ? (
          <Text type="secondary">加载中…</Text>
        ) : docs.length === 0 ? (
          <Empty description="还没有入库内容，上面传一篇试试" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <List
            size="small"
            dataSource={docs}
            renderItem={(d) => (
              <List.Item
                actions={[
                  <Popconfirm key="del" title="删除这篇？" okText="删" cancelText="留" onConfirm={() => void remove(d.title)}>
                    <Button type="text" size="small" danger>
                      删除
                    </Button>
                  </Popconfirm>,
                ]}
              >
                <List.Item.Meta
                  title={<Text strong>{d.title}</Text>}
                  description={
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {d.source ? `来源 ${d.source}` : '手动录入'}
                      {d.created_at ? ` · ${String(d.created_at).slice(0, 10)}` : ''}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        )}

        {hits !== null && (
          <div style={{ marginTop: 14, borderTop: '1px dashed var(--jp-line, #e5e9f0)', paddingTop: 12 }}>
            <Text strong style={{ fontSize: 13 }}>
              检索结果（{hits.length}）
            </Text>
            {hits.length === 0 ? (
              <Paragraph style={{ marginTop: 6, marginBottom: 0, fontSize: 12.5, color: 'var(--jp-ink-3)' }}>
                没有匹配的内容——换个说法试试，比如"海滩""高铁"。
              </Paragraph>
            ) : (
              hits.map((h, i) => (
                <div key={i} style={{ marginTop: 8 }}>
                  <Text strong style={{ fontSize: 13 }}>
                    {h.title}
                  </Text>
                  {h.similarity != null && (
                    <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                      相似度 {Number(h.similarity).toFixed(2)}
                    </Text>
                  )}
                  <div style={{ fontSize: 12.5, color: 'var(--jp-ink-2)' }}>
                    {(h.content ?? '').slice(0, 160)}…
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </Space>
  )
}
