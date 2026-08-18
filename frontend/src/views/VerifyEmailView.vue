<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Message, RefreshRight, Warning } from '@element-plus/icons-vue'

import { api, errorMessage } from '../api/client'

const route = useRoute()
const router = useRouter()
const state = ref(route.query.sent === '1' ? 'sent' : 'idle')
const detail = ref(route.query.sent === '1' ? `验证邮件已发送至 ${route.query.email || '你的邮箱'}` : '')
const resendEmail = ref('')
const resending = ref(false)

const title = computed(() => ({
  verifying: '正在验证邮箱…',
  success: '邮箱验证成功',
  error: '验证没有完成',
  sent: '请查收验证邮件',
  idle: '验证你的邮箱',
}[state.value]))

async function verify(token) {
  state.value = 'verifying'
  detail.value = '正在安全校验验证链接，请稍候。'
  try {
    const { data } = await api.post('/auth/verify-email', { token })
    state.value = 'success'
    detail.value = data.message
    await router.replace({ name: 'verify-email', query: { status: 'success' } })
  } catch (error) {
    state.value = 'error'
    detail.value = errorMessage(error, '验证链接无效或已经过期')
    await router.replace({ name: 'verify-email', query: { status: 'error' } })
  }
}

async function resend() {
  if (!resendEmail.value.trim()) {
    ElMessage.warning('请输入注册时使用的邮箱')
    return
  }
  resending.value = true
  try {
    const { data } = await api.post('/auth/resend-verification', { email: resendEmail.value.trim() })
    state.value = 'sent'
    detail.value = data.message
    ElMessage.success(data.message)
  } catch (error) {
    ElMessage.error(errorMessage(error, '验证邮件发送失败'))
  } finally {
    resending.value = false
  }
}

onMounted(() => {
  const token = typeof route.query.token === 'string' ? route.query.token : ''
  if (token) verify(token)
})
</script>

<template>
  <main class="verify-page">
    <section class="verify-card">
      <div class="verify-brand"><span>C♥</span> CampusMatch</div>
      <div class="verify-icon" :class="state">
        <el-icon v-if="state === 'success'"><Check /></el-icon>
        <el-icon v-else-if="state === 'error'"><Warning /></el-icon>
        <el-icon v-else-if="state === 'verifying'" class="is-loading"><RefreshRight /></el-icon>
        <el-icon v-else><Message /></el-icon>
      </div>
      <p class="verify-eyebrow">EMAIL VERIFICATION</p>
      <h1>{{ title }}</h1>
      <p class="verify-detail">{{ detail || '点击邮件中的验证链接后，才可以登录 CampusMatch。验证链接有效期为 24 小时。' }}</p>

      <RouterLink v-if="state === 'success'" class="primary-pill verify-login" to="/auth">前往登录</RouterLink>

      <div v-else-if="state !== 'verifying'" class="resend-box">
        <label for="resend-email">没有收到，或链接已过期？</label>
        <div>
          <el-input id="resend-email" v-model="resendEmail" type="email" placeholder="输入注册邮箱" @keyup.enter="resend" />
          <button class="secondary-pill" :disabled="resending" @click="resend">
            {{ resending ? '发送中…' : '重新发送' }}
          </button>
        </div>
        <small>同一邮箱 24 小时内只发送一次；同一 IP/邮箱每小时最多请求 3 次。</small>
      </div>

      <RouterLink v-if="state !== 'success'" class="back-login" to="/auth">返回登录</RouterLink>
    </section>
  </main>
</template>

<style scoped>
.verify-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 18px;
  background:
    radial-gradient(circle at 18% 18%, rgba(78, 205, 196, .22), transparent 30%),
    radial-gradient(circle at 82% 16%, rgba(255, 230, 109, .36), transparent 28%),
    linear-gradient(145deg, #fff8f4, #effcf9);
}

.verify-card {
  width: min(560px, 100%);
  padding: 42px;
  text-align: center;
  border: 1px solid rgba(255, 255, 255, .9);
  border-radius: 32px;
  background: rgba(255, 255, 255, .94);
  box-shadow: 0 28px 80px rgba(55, 87, 91, .14);
}

.verify-brand { color: #334748; font-size: 19px; font-weight: 900; letter-spacing: -.4px; }
.verify-brand span { color: #ff6b6b; }
.verify-icon {
  width: 88px;
  height: 88px;
  display: grid;
  place-items: center;
  margin: 30px auto 20px;
  color: #4ecdc4;
  border-radius: 28px;
  background: #e8fbf8;
  font-size: 44px;
}
.verify-icon.success { color: #2fa890; background: #e7faf3; }
.verify-icon.error { color: #ff6b6b; background: #fff0ed; }
.verify-eyebrow { margin: 0 0 8px; color: #d79e28; font-size: 11px; font-weight: 900; letter-spacing: 2px; }
h1 { margin: 0; color: #263a3b; font-size: clamp(28px, 5vw, 38px); }
.verify-detail { max-width: 420px; margin: 14px auto 26px; color: #718182; font-size: 15px; line-height: 1.8; }
.verify-login { display: inline-flex; justify-content: center; min-width: 180px; text-decoration: none; }
.resend-box { margin-top: 22px; padding: 20px; text-align: left; border-radius: 20px; background: #f7fbfa; }
.resend-box label { display: block; margin-bottom: 10px; color: #3d5152; font-size: 14px; font-weight: 800; }
.resend-box > div { display: grid; grid-template-columns: 1fr auto; gap: 10px; }
.resend-box small { display: block; margin-top: 10px; color: #8a9999; line-height: 1.6; }
.back-login { display: inline-block; margin-top: 24px; color: #4b8d88; font-size: 13px; font-weight: 800; text-decoration: none; }
@media (max-width: 560px) {
  .verify-card { padding: 30px 20px; border-radius: 25px; }
  .resend-box > div { grid-template-columns: 1fr; }
}
</style>
