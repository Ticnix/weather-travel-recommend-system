<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../store/auth'
import * as Icons from '@element-plus/icons-vue'
import type { Component } from 'vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

interface MenuItem {
  path: string
  title: string
  icon?: string
  children?: MenuItem[]
}

const menus: MenuItem[] = [
  { path: '/dashboard', title: '数据总览', icon: 'DataBoard' },
  { path: '/weather', title: '气象大数据管理', icon: 'PartlyCloudy' },
  { path: '/news', title: '资讯公告管理', icon: 'Notebook' },
  { path: '/feedback', title: '用户反馈管理', icon: 'ChatDotRound' },
  { path: '/stat', title: '时序统计分析', icon: 'TrendCharts' },
  { path: '/clean', title: '原始数据清洗', icon: 'DataAnalysis' },
  { path: '/sync', title: '天气数据同步', icon: 'Refresh' },
]

function icon(name?: string): Component | undefined {
  if (!name) return undefined
  const map = Icons as Record<string, Component>
  return map[name]
}

const activeMenu = computed(() => route.path)

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="layout">
    <!-- 侧边栏 -->
    <el-aside width="220px" class="sidebar">
      <div class="logo-title">
        <span>🌤️</span>
        <b>气象管理后台</b>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#1f2937"
        text-color="#cbd5e1"
        active-text-color="#ffffff"
        class="side-menu"
      >
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          <el-icon><component :is="icon(m.icon)" /></el-icon>
          <span>{{ m.title }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶栏 -->
      <el-header class="topbar">
        <div class="page-title">{{ route.meta.title }}</div>
        <el-dropdown @command="onLogout">
          <span class="user-chip">
            <el-avatar :size="30" style="background: #3b82f6">{{ auth.displayName[0] }}</el-avatar>
            <span>{{ auth.displayName }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <!-- 内容区 -->
      <el-main class="content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100vh;
}
.sidebar {
  background: #1f2937;
  display: flex;
  flex-direction: column;
}
.logo-title {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 60px;
  padding: 0 18px;
  color: #fff;
  font-size: 15px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.side-menu {
  border-right: none;
  flex: 1;
}
.side-menu :deep(.el-menu-item.is-active) {
  background: #3b82f6;
}
.side-menu :deep(.el-menu-item:hover) {
  background: rgba(59, 130, 246, 0.2);
}
.topbar {
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #374151;
  outline: none;
}
.content {
  background: #f5f7fa;
  padding: 20px;
}
</style>
