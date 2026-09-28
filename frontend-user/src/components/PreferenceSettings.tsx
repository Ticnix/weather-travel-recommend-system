/**
 * 偏好设置区块（Day 56）。
 *
 * 设计要点：
 * - **选项全部用点选**（计划明确要求，不搞自由文本）：手机上打字成本高，
 *   勾选几乎是零成本；仅忌口保留一个短输入（这类信息没法枚举）
 * - **展示效果说明**：用户有权知道"系统记住了什么、会用在哪"（可解释、可撤销）
 * - **一键清空**：撤销入口必须和录入入口一样好找，否则用户会觉得被"记住"了却摆脱不掉
 */

import { useEffect, useState } from 'react'
import {
  Button,
  Checkbox,
  Col,
  Input,
  Popconfirm,
  Row,
  Select,
  Space,
  Typography,
  message,
} from 'antd'
import {
  getMyPreferences,
  updateMyPreferences,
  PREFERENCE_DEFAULTS,
  type UserPreferenceData,
} from '../api/preferences'

const { Paragraph, Text, Title } = Typography

/** 勾选组：key 对应后端 schema 字段；hint 用于 hover 说明这一项会影响什么 */
const BOOL_GROUPS: {
  title: string
  options: { key: BoolKey; label: string }[]
}[] = [
  {
    title: '身体状况',
    options: [
      { key: 'sun_sensitive', label: '怕晒' },
      { key: 'cold_sensitive', label: '怕冷' },
    ],
  },
  {
    title: '同行人',
    options: [
      { key: 'with_elderly', label: '有老人' },
      { key: 'with_children', label: '有小孩' },
      { key: 'with_pet', label: '带宠物' },
    ],
  },
  {
    title: '活动偏好',
    options: [
      { key: 'prefer_outdoor', label: '偏爱户外' },
      { key: 'prefer_indoor', label: '偏爱室内' },
      { key: 'prefer_photo', label: '爱拍照' },
      { key: 'prefer_food', label: '爱美食' },
    ],
  },
  {
    title: '预算',
    options: [{ key: 'budget_low', label: '预算有限' }],
  },
]

type BoolKey = Exclude<keyof UserPreferenceData, 'commute' | 'diet'>

const COMMUTE_OPTIONS = ['地铁', '公交', '自驾', '步行', '骑行', '打车'].map((v) => ({
  value: v,
  label: v,
}))

export default function PreferenceSettings() {
  const [data, setData] = useState<UserPreferenceData | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getMyPreferences()
      .then(setData)
      .catch(() => setLoadFailed(true))
  }, [])

  const toggle = (key: BoolKey, checked: boolean) => {
    setData((prev) => (prev ? { ...prev, [key]: checked } : prev))
  }

  const save = async (next: UserPreferenceData, okText: string) => {
    setSaving(true)
    try {
      setData(await updateMyPreferences(next))
      message.success(okText)
    } catch {
      // 失败原因（未登录 / 网络问题）由全局拦截器提示，这里只保持表单不动
    } finally {
      setSaving(false)
    }
  }

  if (loadFailed) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        <Title level={4} className="jp-serif" style={{ margin: 0 }}>
          我的偏好
        </Title>
        <Paragraph style={{ marginTop: 8, color: 'var(--jp-ink-2)' }}>
          偏好暂时读不出来（网络问题），稍后重试即可；不影响其它功能。
        </Paragraph>
        <Button onClick={() => window.location.reload()}>重试</Button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="jp-card" style={{ padding: 24 }}>
        <Text type="secondary">正在读取你的偏好…</Text>
      </div>
    )
  }

  return (
    <div className="jp-card" style={{ padding: 24 }}>
      <div style={{ marginBottom: 4 }}>
        <span className="jp-serif" style={{ fontSize: 16, fontWeight: 600 }}>
          我的偏好
        </span>
      </div>
      <Paragraph style={{ marginBottom: 12, color: 'var(--jp-ink-2)', fontSize: 13 }}>
        保存后会用在：<b>AI 对话</b>（比如自动避开正午暴晒、放缓带老人的行程）、
        <b>行程排程</b>和<b>推荐排序</b>。随时可以取消勾选或一键清空。
      </Paragraph>

      {/* 体质三选一（原 Day 37 组件）已按用户要求移除：
          它影响的是生活指数排序，与下面的 AI 偏好重叠观感太强；
          后端 body_preference 字段与逻辑保留，需要时可在管理端恢复入口 */}

      <Space direction="vertical" size={14} style={{ width: '100%' }}>
        {BOOL_GROUPS.map((group) => (
          <div key={group.title}>
            <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 13 }}>
              {group.title}
            </Text>
            <Row gutter={[12, 8]}>
              {group.options.map((opt) => (
                <Col key={opt.key}>
                  <Checkbox
                    checked={data[opt.key]}
                    onChange={(e) => toggle(opt.key, e.target.checked)}
                  >
                    {opt.label}
                  </Checkbox>
                </Col>
              ))}
            </Row>
          </div>
        ))}

        <Row gutter={12}>
          <Col xs={24} sm={12}>
            <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 13 }}>
              主要通勤方式
            </Text>
            <Select
              value={data.commute || undefined}
              options={COMMUTE_OPTIONS}
              placeholder="选择常用出行方式"
              allowClear
              style={{ width: '100%' }}
              onChange={(v) => setData({ ...data, commute: v ?? '' })}
            />
          </Col>
          <Col xs={24} sm={12}>
            <Text strong style={{ display: 'block', marginBottom: 8, fontSize: 13 }}>
              忌口 / 饮食注意（30 字内）
            </Text>
            <Input
              value={data.diet}
              maxLength={30}
              placeholder="如：不吃辣、海鲜过敏"
              onChange={(e) => setData({ ...data, diet: e.target.value })}
            />
          </Col>
        </Row>

        <Row justify="space-between" align="middle">
          <Popconfirm
            title="确定清空全部偏好？"
            description="清空后 AI 将不再参考任何偏好。"
            okText="清空"
            cancelText="再想想"
            onConfirm={() => void save({ ...PREFERENCE_DEFAULTS }, '已清空偏好')}
          >
            <Button danger type="text" size="small" loading={saving}>
              一键清空
            </Button>
          </Popconfirm>
          <Button
            type="primary"
            loading={saving}
            onClick={() => void save(data, '偏好已保存，之后的回答会参考它们')}
          >
            保存
          </Button>
        </Row>
      </Space>
    </div>
  )
}
