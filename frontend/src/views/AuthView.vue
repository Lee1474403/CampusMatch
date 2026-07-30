<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowRight, Check, Lock, Message, School, UserFilled } from '@element-plus/icons-vue'

import { errorMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const mode = ref('login')
const submitting = ref(false)

const loginForm = reactive({ identifier: '20260006', password: 'Campus123' })
const registerForm = reactive({
  account: '', phone: '', email: '', password: '', gender: 'male', real_name: '', nickname: '',
  birth_date: '2005-01-01', school: '', department: '', grade: '',
})

async function submitLogin() {
  submitting.value = true
  try {
    await auth.login(loginForm)
    ElMessage.success(`欢迎回来，${auth.user.nickname}`)
    router.replace(route.query.next || '/discover')
  } catch (error) {
    ElMessage.error(errorMessage(error, '登录失败'))
  } finally {
    submitting.value = false
  }
}

async function submitRegister() {
  submitting.value = true
  try {
    await auth.register({
      ...registerForm,
      real_name: registerForm.real_name || null,
      department: registerForm.department.trim() || null,
    })
    ElMessage.success('注册成功，先选几个喜欢的标签吧')
    router.replace('/profile')
  } catch (error) {
    ElMessage.error(errorMessage(error, '注册失败'))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <section class="auth-story">
      <div class="auth-brand"><span>C♥</span> CampusMatch</div>
      <div class="story-copy">
        <p class="eyebrow">只属于校园的心动频道</p>
        <h1>从一个共同爱好，<br />聊到<span>刚好同频。</span></h1>
        <p>不追求无尽滑动。每天中午十二点，只为你安排一位互为唯一的校园配对，慢一点，也认真一点。</p>
        <div class="story-points">
          <span><el-icon><Check /></el-icon> 校园身份</span>
          <span><el-icon><Check /></el-icon> 兴趣匹配</span>
          <span><el-icon><Check /></el-icon> 双向心动</span>
        </div>
      </div>
      <div class="orbit-card card-one"><b>🎧 音乐</b><small>共同兴趣 +1</small></div>
      <div class="orbit-card card-two"><span>91%</span><small>同频指数</small></div>
      <div class="campus-ticket"><span>今天的遇见</span><b>1</b><small>互为唯一，慢慢认识</small></div>
    </section>

    <section class="auth-panel">
      <div class="auth-box" :class="{ wide: mode === 'register' }">
        <div class="auth-tabs" role="tablist">
          <button :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
          <button :class="{ active: mode === 'register' }" @click="mode = 'register'">加入 CampusMatch</button>
        </div>

        <div v-if="mode === 'login'" class="form-stage">
          <div class="form-heading"><p>欢迎回来 👋</p><h2>继续你的校园故事</h2></div>
          <el-form size="large" @submit.prevent="submitLogin">
            <el-form-item>
              <el-input v-model="loginForm.identifier" autocomplete="username" placeholder="账号 / 手机号 / 邮箱" :prefix-icon="UserFilled" />
            </el-form-item>
            <el-form-item>
              <el-input v-model="loginForm.password" autocomplete="current-password" show-password type="password" placeholder="密码" :prefix-icon="Lock" @keyup.enter="submitLogin" />
            </el-form-item>
            <button class="primary-pill full" :disabled="submitting" @click.prevent="submitLogin">
              {{ submitting ? '正在登录…' : '进入 CampusMatch' }} <el-icon><ArrowRight /></el-icon>
            </button>
          </el-form>
          <div class="demo-account">
            <span>✨ 试用账号已填好</span>
            <small>男生：20260006　女生：20260001　密码：Campus123</small>
          </div>
          <p class="safety-note"><el-icon><Lock /></el-icon> 双方心动后开放聊天，连续聊满7天才解锁隐私</p>
        </div>

        <div v-else class="form-stage register-stage">
          <div class="form-heading"><p>认识你，从基本信息开始</p><h2>创建校园名片</h2></div>
          <el-form label-position="top" @submit.prevent="submitRegister">
            <div class="form-grid">
              <el-form-item label="账号">
                <el-input v-model="registerForm.account" autocomplete="username" placeholder="例如 nwpu123456" />
                <small class="account-hint">账号需与其他用户不同，建议使用“学校缩写 + 学号”创建，例如 nwpu123456；这只是建议写法。</small>
              </el-form-item>
              <el-form-item label="昵称"><el-input v-model="registerForm.nickname" placeholder="想让大家怎么称呼你" /></el-form-item>
              <el-form-item label="手机号"><el-input v-model="registerForm.phone" placeholder="用于登录" /></el-form-item>
              <el-form-item label="校园邮箱"><el-input v-model="registerForm.email" placeholder="name@university.edu.cn" /></el-form-item>
              <el-form-item label="密码"><el-input v-model="registerForm.password" type="password" show-password placeholder="至少 8 位，含字母和数字" /></el-form-item>
              <el-form-item label="性别（注册后不可改）">
                <el-radio-group v-model="registerForm.gender"><el-radio-button value="male">男生</el-radio-button><el-radio-button value="female">女生</el-radio-button></el-radio-group>
              </el-form-item>
              <el-form-item label="生日"><el-date-picker v-model="registerForm.birth_date" value-format="YYYY-MM-DD" type="date" placeholder="选择生日" /></el-form-item>
              <el-form-item label="真实姓名（可选，仅自己可见）"><el-input v-model="registerForm.real_name" placeholder="不会向其他用户公开" /></el-form-item>
              <el-form-item label="学校（必填）"><el-input v-model="registerForm.school" placeholder="请输入学校全称" :prefix-icon="School" /></el-form-item>
              <el-form-item label="专业/院系（可选）"><el-input v-model="registerForm.department" placeholder="如 计算机学院·软件工程" /></el-form-item>
              <el-form-item label="年级"><el-input v-model="registerForm.grade" placeholder="例如 大一、研二" /></el-form-item>
            </div>
            <button class="primary-pill full" :disabled="submitting" @click.prevent="submitRegister">
              {{ submitting ? '正在创建…' : '创建账号' }} <el-icon><ArrowRight /></el-icon>
            </button>
          </el-form>
          <p class="agreement">注册即表示你愿意共同维护真实、尊重、健康的校园社交环境。</p>
        </div>
      </div>
    </section>
  </div>
</template>
