<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { currentWeather, historyList, forecast, type HistoryRecord } from '../api/weather'

const now = ref<HistoryRecord | null>(null)
const recentCount = ref(0)
const forecastCount = ref(0)

const cards = [
  { title: '气象时序记录', value: '--', suffix: '条', icon: '🕒', color: '#3b82f6' },
  { title: '7 天预报', value: '--', suffix: '天', icon: '📅', color: '#10b981' },
  { title: '当前温度', value: '--', suffix: '°C', icon: '🌡️', color: '#f59e0b' },
]

function fillCards() {
  if (now.value) {
    cards[2].value = String(now.value.temperature ?? '--')
  }
  cards[0].value = String(recentCount.value)
  cards[1].value = String(forecastCount.value)
}

onMounted(async () => {
  try {
    now.value = await currentWeather()
  } catch {
    now.value = null
  }
  try {
    const h = await historyList(30)
    recentCount.value = h.total
  } catch {
    recentCount.value = 0
  }
  try {
    const f = await forecast()
    forecastCount.value = f.total
  } catch {
    forecastCount.value = 0
  }
  fillCards()
})
</script>

<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="8" v-for="c in cards" :key="c.title">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-icon" :style="{ background: c.color + '1a', color: c.color }">
            {{ c.icon }}
          </div>
          <div>
            <div class="stat-value">
              {{ c.value }}<small>{{ c.suffix }}</small>
            </div>
            <div class="stat-title">{{ c.title }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="now-card" v-if="now">
      <template #header><b>最新实测天气</b></template>
      <div class="now-grid">
        <div class="now-item"><span>天气</span><b>{{ now.weather_desc || '--' }}</b></div>
        <div class="now-item"><span>温度</span><b>{{ now.temperature }}°C</b></div>
        <div class="now-item"><span>体感</span><b>{{ now.feels_like }}°C</b></div>
        <div class="now-item"><span>湿度</span><b>{{ now.humidity }}%</b></div>
        <div class="now-item"><span>风速</span><b>{{ now.wind_speed }} km/h</b></div>
        <div class="now-item"><span>风向</span><b>{{ now.wind_direction || '--' }}</b></div>
        <div class="now-item"><span>气压</span><b>{{ now.pressure }} hPa</b></div>
        <div class="now-item"><span>能见度</span><b>{{ now.visibility }} km</b></div>
        <div class="now-item"><span>更新时间</span><b>{{ String(now.time).replace('T', ' ').slice(0, 19) }}</b></div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 16px;
}
.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26px;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #1f2937;
}
.stat-value small {
  font-size: 13px;
  font-weight: 400;
  color: #9ca3af;
  margin-left: 2px;
}
.stat-title {
  font-size: 13px;
  color: #9ca3af;
  margin-top: 2px;
}
.now-card {
  margin-top: 16px;
}
.now-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px 24px;
}
.now-item span {
  display: block;
  font-size: 13px;
  color: #9ca3af;
}
.now-item b {
  font-size: 18px;
  color: #1f2937;
}
</style>
