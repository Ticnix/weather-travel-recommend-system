<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { currentWeather, syncNow, syncHistory, historyList, type HistoryRecord } from '../api/weather'

const now = ref<HistoryRecord | null>(null)
const recent = ref<HistoryRecord[]>([])
const syncing = ref(false)
const backfillDays = ref(30)

async function load() {
  try {
    now.value = await currentWeather()
  } catch {
    now.value = null
  }
  try {
    const r = await historyList(30)
    recent.value = r.items
  } catch {
    recent.value = []
  }
}

async function onSync() {
  syncing.value = true
  try {
    const res: any = await syncNow()
    ElMessage.success(`同步成功：${res.temperature ?? ''}°C ${res.weather_desc ?? ''}`)
    load()
  } catch {
    /* 拦截器提示 */
  } finally {
    syncing.value = false
  }
}

async function onBackfill() {
  await ElMessageBox.confirm(
    `将调用 Open-Meteo 回补过去 ${backfillDays.value} 天的日统计作为实测入库，是否继续？`,
    '历史回补',
    { type: 'warning' },
  )
  try {
    const res: any = await syncHistory(backfillDays.value)
    ElMessage.success(res.message || '历史回补完成')
    load()
  } catch {
    /* 拦截器提示 */
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header><b>手动天气同步</b></template>
      <el-space wrap>
        <el-button type="primary" :loading="syncing" @click="onSync">立即同步（实时 + 7 天预报）</el-button>
        <el-space>
          <el-input-number v-model="backfillDays" :min="1" :max="92" style="width: 120px" />
          <span>天历史回补</span>
          <el-button @click="onBackfill">回补历史数据</el-button>
        </el-space>
      </el-space>
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header><b>当前最新实测</b></template>
      <el-descriptions v-if="now" :column="4" border>
        <el-descriptions-item label="天气">{{ now.weather_desc || '--' }}</el-descriptions-item>
        <el-descriptions-item label="温度">{{ now.temperature }}°C</el-descriptions-item>
        <el-descriptions-item label="体感">{{ now.feels_like }}°C</el-descriptions-item>
        <el-descriptions-item label="湿度">{{ now.humidity }}%</el-descriptions-item>
        <el-descriptions-item label="风速">{{ now.wind_speed }} km/h</el-descriptions-item>
        <el-descriptions-item label="气压">{{ now.pressure }} hPa</el-descriptions-item>
        <el-descriptions-item label="更新时间" :span="2">
          {{ String(now.time).replace('T', ' ').slice(0, 19) }}
        </el-descriptions-item>
      </el-descriptions>
      <el-empty v-else description="暂无数据，请先同步" />
    </el-card>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header><b>最近 30 条实测记录</b></template>
      <el-table :data="recent" border stripe max-height="420">
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ String(row.time).replace('T', ' ').slice(0, 19) }}</template>
        </el-table-column>
        <el-table-column prop="weather_desc" label="天气" width="100" />
        <el-table-column prop="temperature" label="温度°C" width="90" />
        <el-table-column prop="humidity" label="湿度%" width="80" />
        <el-table-column prop="wind_speed" label="风速 km/h" width="110" />
        <el-table-column prop="precipitation" label="降水 mm" />
      </el-table>
    </el-card>
  </div>
</template>
