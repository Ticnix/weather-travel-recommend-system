<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '../store/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const form = reactive({ username: 'admin', password: '' })
const loading = ref(false)

async function handleLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/dashboard'
    router.push(redirect)
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card" shadow="always">
      <div class="brand">
        <div class="logo">🌤️</div>
        <h2>气象出行推荐 · 管理后台</h2>
        <p>广州气象大数据 & AI 出行推荐系统</p>
      </div>
      <el-form :model="form" label-position="top" @keyup.enter="handleLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="管理员账号" :prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-button type="primary" size="large" style="width: 100%" :loading="loading" @click="handleLogin">
          登 录
        </el-button>
      </el-form>
      <div class="hint">默认管理员：admin</div>
    </el-card>
  </div>
</template>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef2f7 0%, #dfe7ef 100%);
}
.login-card {
  width: 380px;
  padding: 12px 8px;
  border-radius: 12px;
}
.brand {
  text-align: center;
  margin-bottom: 20px;
}
.logo {
  font-size: 44px;
}
.brand h2 {
  margin: 8px 0 4px;
  font-size: 20px;
  color: #1f2937;
}
.brand p {
  margin: 0;
  font-size: 13px;
  color: #9ca3af;
}
.hint {
  margin-top: 14px;
  text-align: center;
  font-size: 12px;
  color: #9ca3af;
}
</style>
