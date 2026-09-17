<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts/core'
import type { ECharts } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  analysisCompare,
  analysisDaily,
  refreshAggregate,
  type CompareResult,
  type DailyPoint,
} from '../api/weather'

// 按需注册：只打包用到的图表与组件，避免把整个 ECharts 打进 chunk
echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const chartEl = ref<HTMLDivElement | null>(null)
const days = ref(90)
const loading = ref(false)
const refreshing = ref(false)
const compare = ref<{ yoy?: CompareResult; mom?: CompareResult }>({})
let chart: ECharts | null = null

/** 图例：温度区间带（最高/最低之间）+ 均温线 + 降水累计柱 */
async function render() {
  const res = await analysisDaily(days.value)
  const items: DailyPoint[] = res.items
  const dates = items.map((i) => i.date.slice(5))
  const lows = items.map((i) => i.temp_min ?? 0)
  // 区间带 = 最高 - 最低（下界用 stack 技巧画在低温之上）
  const band = items.map((i) => (i.temp_max ?? 0) - (i.temp_min ?? 0))
  const highs = items.map((i) => i.temp_max)
  const precip = items.map((i) => i.precip_sum ?? 0)

  if (!chart && chartEl.value) {
    chart = echarts.init(chartEl.value)
  }
  chart?.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['最高/最低区间 (°C)', '日均温度 (°C)', '降水累计 (mm)'], top: 0 },
    grid: { left: 50, right: 55, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10 } },
    yAxis: [
      { type: 'value', name: '温度 °C', position: 'left' },
      { type: 'value', name: '降水 mm', position: 'right', axisLabel: { formatter: '{value} mm' } },
    ],
    series: [
      {
        name: '最低温',
        type: 'line',
        data: lows,
        stack: 'band',
        lineStyle: { opacity: 0 },
        symbol: 'none',
        silent: true,
        tooltip: { show: false },
      },
      {
        name: '最高/最低区间 (°C)',
        type: 'line',
        data: band,
        stack: 'band',
        lineStyle: { opacity: 0 },
        symbol: 'none',
        areaStyle: { color: '#f59e0b', opacity: 0.18 },
      },
      {
        name: '日均温度 (°C)',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#ef4444' },
        lineStyle: { width: 2.5 },
        data: highs.map((_, i) => items[i].temp_avg),
      },
      {
        name: '降水累计 (mm)',
        type: 'bar',
        yAxisIndex: 1,
        barMaxWidth: 12,
        itemStyle: { color: '#3b82f6' },
        data: precip,
      },
    ],
  })
}

/** 同比 / 环比：两路并行，任一侧无数据由后端如实说明 */
async function loadCompare() {
  try {
    const [yoy, mom] = await Promise.all([analysisCompare('yoy'), analysisCompare('mom')])
    compare.value = { yoy, mom }
  } catch {
    /* 拦截器提示 */
  }
}

async function reload() {
  loading.value = true
  try {
    await Promise.all([render(), loadCompare()])
  } catch {
    /* 拦截器提示 */
  } finally {
    loading.value = false
  }
}

async function onRefresh() {
  refreshing.value = true
  try {
    const res = await refreshAggregate()
    if (res.refreshed) {
      ElMessage.success('连续聚合已刷新')
      await Promise.all([render(), loadCompare()])
    } else {
      ElMessage.warning('刷新失败，请查看后端日志')
    }
  } catch {
    /* 拦截器提示 */
  } finally {
    refreshing.value = false
  }
}

function fmt(value: number | null | undefined, unit: string, digits = 1): string {
  if (value === null || value === undefined) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(digits)}${unit}`
}

function onResize() {
  chart?.resize()
}

onMounted(async () => {
  await reload()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <el-card shadow="never">
    <template #header>
      <div class="hd">
        <b>气象时序统计分析</b>
        <div class="ops">
          <el-radio-group v-model="days" :disabled="loading" @change="reload">
            <el-radio-button :value="7">近 7 天</el-radio-button>
            <el-radio-button :value="30">近 30 天</el-radio-button>
            <el-radio-button :value="90">近 90 天</el-radio-button>
            <el-radio-button :value="365">近 1 年</el-radio-button>
          </el-radio-group>
          <el-tooltip content="回补历史数据后手动刷新，不必等下一个整点" placement="top">
            <el-button :loading="refreshing" @click="onRefresh">刷新聚合</el-button>
          </el-tooltip>
        </div>
      </div>
    </template>

    <div ref="chartEl" class="chart" />

    <el-row :gutter="16" class="cmp">
      <el-col :span="12" v-for="key in (['yoy', 'mom'] as const)" :key="key">
        <div class="card" v-if="compare[key]">
          <div class="card-hd">
            <b>{{ compare[key]!.kind_label }}</b>
            <span class="period">{{ compare[key]!.current_period }} vs {{ compare[key]!.previous_period }}</span>
          </div>

          <template v-if="compare[key]!.available">
            <div class="metrics">
              <div class="metric">
                <span class="label">气温</span>
                <span class="value">{{ fmt(compare[key]!.diff.temp_avg, '°C') }}</span>
              </div>
              <div class="metric">
                <span class="label">降水</span>
                <span class="value">{{ fmt(compare[key]!.diff.precip_total, 'mm') }}</span>
              </div>
              <div class="metric">
                <span class="label">湿度</span>
                <span class="value">{{ fmt(compare[key]!.diff.humidity_avg, '%') }}</span>
              </div>
            </div>
            <div class="verdict">{{ compare[key]!.verdict }}</div>
            <div class="note">{{ compare[key]!.sample_note }}</div>
          </template>
          <el-empty :description="compare[key]!.reason" :image-size="60" v-else />
        </div>
      </el-col>
    </el-row>
  </el-card>
</template>

<style scoped>
.hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ops {
  display: flex;
  gap: 12px;
  align-items: center;
}
.chart {
  width: 100%;
  height: 420px;
}
.cmp {
  margin-top: 16px;
}
.card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
  min-height: 150px;
}
.card-hd {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
}
.period {
  color: #6b7280;
  font-size: 12px;
}
.metrics {
  display: flex;
  gap: 24px;
}
.metric .label {
  display: block;
  color: #9ca3af;
  font-size: 12px;
}
.metric .value {
  font-size: 20px;
  font-weight: 600;
}
.verdict {
  margin-top: 12px;
  color: #111827;
}
.note {
  margin-top: 6px;
  color: #9ca3af;
  font-size: 12px;
}
</style>
