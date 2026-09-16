import { useEffect, useState } from 'react'
import { Segmented, Space, Typography, message } from 'antd'
import http from '../api/http'
import { fetchMe, getStoredUser, type AuthUser } from '../api/auth'

const { Text } = Typography

const OPTIONS = [
  { label: '普通', value: 'normal' },
  { label: '怕冷', value: 'cold' },
  { label: '怕热', value: 'heat' },
]

const HINTS: Record<string, string> = {
  normal: '按通用权重展示生活指数',
  cold: '穿衣、感冒、舒适度指数优先展示',
  heat: '舒适度、防晒、空调指数优先展示',
}

/**
 * 体质偏好设置（Day 37）。
 *
 * 它影响的是生活指数的**排序**而不是内容：同一批官方指数，
 * 怕冷的人先看到穿衣与感冒，怕热的人先看到舒适度与防晒。
 */
export default function BodyPreferenceSetting() {
  const [value, setValue] = useState('normal')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    // 本地缓存可能过期（比如换设备登录过），以服务端为准再取一次
    const cached = getStoredUser()
    if (cached?.body_preference) setValue(cached.body_preference)
    void fetchMe()
      .then((me) => setValue(me.body_preference || 'normal'))
      .catch(() => {})
  }, [])

  const handleChange = async (next: string) => {
    if (next === value) return
    const prev = value
    setValue(next)
    setSaving(true)
    try {
      const user = getStoredUser()
      if (!user) return
      const updated = (await http.put(`/users/${user.id}`, {
        body_preference: next,
      })) as unknown as AuthUser
      // 同步本地缓存，刷新后首屏就是新偏好
      localStorage.setItem('wt_user', JSON.stringify({ ...user, ...updated }))
      message.success('偏好已保存')
    } catch {
      // 保存失败必须回滚，否则界面显示的是没生效的状态
      setValue(prev)
      message.error('保存失败，请稍后重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Text style={{ fontWeight: 600 }}>体质偏好</Text>
        {saving ? <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>保存中…</Text> : null}
      </Space>
      <Segmented
        options={OPTIONS}
        value={value}
        onChange={(v) => void handleChange(String(v))}
      />
      <Text style={{ fontSize: 12, color: 'var(--jp-ink-3)' }}>{HINTS[value]}</Text>
    </Space>
  )
}
