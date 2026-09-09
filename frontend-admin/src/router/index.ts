import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../store/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/Login.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('../layouts/AdminLayout.vue'),
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('../views/Dashboard.vue'),
          meta: { title: '数据总览', icon: 'DataBoard' },
        },
        {
          path: 'weather',
          name: 'weather',
          component: () => import('../views/WeatherData.vue'),
          meta: { title: '气象大数据管理', icon: 'PartlyCloudy' },
        },
        {
          path: 'news',
          name: 'news',
          component: () => import('../views/NewsManage.vue'),
          meta: { title: '资讯公告管理', icon: 'Notebook' },
        },
        {
          path: 'feedback',
          name: 'feedback',
          component: () => import('../views/FeedbackManage.vue'),
          meta: { title: '用户反馈管理', icon: 'ChatDotRound' },
        },
        {
          path: 'stat',
          name: 'stat',
          component: () => import('../views/WeatherStat.vue'),
          meta: { title: '时序统计分析', icon: 'TrendCharts' },
        },
        {
          path: 'clean',
          name: 'clean',
          component: () => import('../views/CleanManage.vue'),
          meta: { title: '原始数据清洗', icon: 'DataAnalysis' },
        },
        {
          path: 'sync',
          name: 'sync',
          component: () => import('../views/WeatherSync.vue'),
          meta: { title: '天气同步', icon: 'Refresh' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.public) {
    if (to.name === 'login' && auth.isLoggedIn) return '/dashboard'
    return true
  }
  if (!auth.isLoggedIn) return { path: '/login', query: { redirect: to.fullPath } }
  if (!auth.isAdmin) {
    return { path: '/login', query: { redirect: to.fullPath }, replace: true }
  }
  return true
})

export default router
