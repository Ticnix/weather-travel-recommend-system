import { Alert, Button, Divider, Modal, Space, Tag, Typography, message } from 'antd'
import { AimOutlined } from '@ant-design/icons'
import { useCallback, useEffect, useState } from 'react'
import { getLocalWeather, listDistricts, type DistrictOption, type LocalWeather } from '../api/weather'
import {
  geoAvailable,
  requestPosition,
  setLocalLocation,
  type LocalLocation,
} from '../utils/localLocation'
import LoadingState from './LoadingState'
import { useIsMobile } from '../utils/useIsMobile'

const { Paragraph, Text } = Typography

/**
 * 区域选择器：决定"首页天气按哪里取数"。
 *
 * 为什么不能只靠浏览器定位：定位会被拒（很多人默认拒绝权限），
 * 室内/高楼也可能定到隔壁区。而"我在南沙，却给我看越秀的天气"是用户一眼能看穿的错误，
 * 所以做成「定位优先，手动选择兜底」，两者都持久化到本地。
 */
export default function LocationPicker({ open, onClose }: { open: boolean; onClose: () => void }) {
  const isMobile = useIsMobile()
  const [districts, setDistricts] = useState<DistrictOption[]>([])
  const [districtsFailed, setDistrictsFailed] = useState(false)
  const [loadingDistricts, setLoadingDistricts] = useState(false)
  // 正在处理的按钮（geo 或某个区名）：按住哪个转哪个，避免整块按钮都转圈
  const [busy, setBusy] = useState<string | null>(null)

  const loadDistricts = useCallback(async () => {
    setLoadingDistricts(true)
    setDistrictsFailed(false)
    try {
      setDistricts(await listDistricts('广州'))
    } catch {
      // 列表取不到不影响"用我的位置"这条主路径，但要说清是"没取到"而不是"没有区"
      setDistricts([])
      setDistrictsFailed(true)
    } finally {
      setLoadingDistricts(false)
    }
  }, [])

  useEffect(() => {
    if (open) void loadDistricts()
  }, [open, loadDistricts])

  const apply = (data: LocalWeather) => {
    const l = data.location
    const next: LocalLocation = {
      city: l.city,
      district: l.district,
      lat: l.lat,
      lon: l.lon,
      source: l.source,
      precision: l.precision,
      label: l.label,
    }
    setLocalLocation(next)
    message.success(
      next.precision === 'district'
        ? `已按「${next.label}」展示天气`
        : `「${next.city}」暂时只能到市中心精度，已按市中心展示`,
    )
    onClose()
  }

  const useCurrentPosition = async () => {
    if (!geoAvailable()) {
      message.warning('当前浏览器不支持定位（需要 HTTPS 环境），请手动选择下面的区')
      return
    }
    setBusy('geo')
    try {
      const pos = await requestPosition()
      if (!pos) {
        // 拒绝授权 / 超时都走这里：不当作错误，只说明并给出替代方案
        message.warning('没拿到位置（可能拒绝了授权或定位超时），可以手动选择下面的区')
        return
      }
      apply(await getLocalWeather({ lat: pos.lat, lon: pos.lon }))
    } catch {
      message.error('定位成功了，但当地天气没取到，请稍后重试或手动选择区')
    } finally {
      setBusy(null)
    }
  }

  const chooseDistrict = async (name: string) => {
    setBusy(name)
    try {
      apply(await getLocalWeather({ district: name }))
    } catch {
      message.error(`「${name}」的天气没取到，请稍后重试`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <Modal
      title="天气按哪个区域展示"
      open={open}
      onCancel={onClose}
      footer={null}
      width={isMobile ? '92%' : 480}
    >
      <Paragraph style={{ color: 'var(--jp-ink-2)', fontSize: 13, marginTop: 0 }}>
        广州南北跨度 100 多公里，南沙和从化同一天能差好几度。选一个区域，首页就按这个区展示天气。
      </Paragraph>

      <Button
        type="primary"
        block
        icon={<AimOutlined />}
        loading={busy === 'geo'}
        onClick={useCurrentPosition}
      >
        使用我的位置（最准）
      </Button>
      <Text style={{ display: 'block', marginTop: 6, fontSize: 12, color: 'var(--jp-ink-3)' }}>
        位置只用来决定展示哪个区的天气，不会写进账号资料。
      </Text>

      <Divider style={{ margin: '16px 0 12px', fontSize: 13 }}>或手动选择</Divider>

      {loadingDistricts ? (
        <LoadingState compact text="正在加载区域列表…" />
      ) : districtsFailed ? (
        <Alert
          type="warning"
          showIcon
          message="区域列表没加载出来"
          description="不影响使用：可以直接用上面的定位，或者稍后重试。"
          action={
            <Button size="small" onClick={() => void loadDistricts()}>
              重试
            </Button>
          }
        />
      ) : districts.length === 0 ? (
        <Text style={{ fontSize: 13, color: 'var(--jp-ink-3)' }}>
          暂时没有可选的区，请先用定位。
        </Text>
      ) : (
        <Space wrap size={8}>
          {districts.map((d) => (
            <Button
              key={d.name}
              size="small"
              loading={busy === d.name}
              onClick={() => void chooseDistrict(d.name)}
              title={
                d.has_coords ? '按该区中心取数' : '该区暂无区中心坐标，将按市中心展示'
              }
            >
              {d.name}
              {!d.has_coords && (
                <Tag style={{ margin: '0 0 0 6px', fontSize: 10, lineHeight: '16px' }}>市中心</Tag>
              )}
            </Button>
          ))}
        </Space>
      )}

      <div style={{ marginTop: 18, textAlign: 'right' }}>
        <Button
          type="link"
          size="small"
          onClick={() => {
            setLocalLocation(null)
            message.info('已恢复为默认城市（广州市中心）')
            onClose()
          }}
        >
          不用区域定位（按广州市中心）
        </Button>
      </div>
    </Modal>
  )
}
