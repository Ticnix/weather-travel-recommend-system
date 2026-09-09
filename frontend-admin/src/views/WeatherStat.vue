<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { weatherStats, type DailyAgg } from '../api/weather'

const chartEl = ref<HTMLDivElement | null>(null)
const days = ref(30)
let chart: echarts.ECharts | null = null

async function render() {
  const res = await weatherStats(days.value)
  const items: DailyAgg[] = res.items
  const dates = items.map((i) => i.date.slice(5))
  const temps = items.map((i) => i.temperature_avg)
  const rains = items.map((i) => i.precipitation_avg)

  if (!chart && chartEl.value) {
    chart = echarts.init(chartEl.value)
  }
  chart?.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['平均温度 (°C)', '降水量 (mm)'], top: 0 },
    grid: { left: 50, right: 50, top: 40, bottom: 30 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 10 },
    },
    yAxis: [
      { type: 'value', name: '温度 °C', position: 'left' },
      { type: 'value', name: '降水 mm', position: 'right', axisLabel: { formatter: '{value} mm' } },
    ],
    series: [
      {
        name: '平均温度 (°C)',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        itemStyle: { color: '#f59e0b' },
        lineStyle: { width: 2.5 },
        areaStyle: { opacity: 0.15 },
        data: temps,
      },
      {
        name: '降水量 (mm)',
        type: 'bar',
        yAxisIndex: 1,
        barMaxWidth: 12,
        itemStyle: { color: '#3b82f6' },
        data: rains,
      },
    ],
  })
}

async function reload() {
  try {
    await render()
  } catch {
    /* 拦截器提示 */
  }
}

function onResize() {
  chart?.resize()
}

onMounted(async () => {
  await reload()
  window.addEventListener('resize', onResize)
  // 容器稳定后再设一次
  await nextTick()
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
        <el-radio-group v-model="days" @change="reload">
          <el-radio-button :value="7">近 7 天</el-radio-button>
          <el-radio-button :value="30">近 30 天</el-radio-button>
          <el-radio-button :value="60">近 60 天</el-radio-button>
          <el-radio-button :value="90">近 90 天</el-radio-button>
        </el-radio-group>
      </div>
    </template>
    <div ref="chartEl" class="chart" />
  </el-card>
</template>

<style scoped>
.hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chart {
  width: 100%;
  height: 480px;
}
</style>
