<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ChatDotRound, Lock, Switch } from '@element-plus/icons-vue'

import { api, errorMessage } from '../api/client'
import AppShell from '../components/AppShell.vue'
import AvatarBubble from '../components/AvatarBubble.vue'

const status = ref(null)
const loading = ref(true)
const saving = ref(false)
const blockDialog = ref(false)
const blockReason = ref('疑似诈骗')
const blocking = ref(false)
const now = ref(Date.now())
let clock = null

const pair = computed(() => status.value?.pair || null)
const stage = computed(() => {
  if (!status.value?.profile_complete) return 'profile'
  if (pair.value?.status === 'pending_heartbeat') return 'heart'
  if (pair.value?.status === 'chatting') return 'chat'
  if (pair.value?.status === 'privacy_unlocked') return 'unlock'
  return status.value?.matching_enabled ? 'waiting' : 'ready'
})

const stages = [
  { key: 'profile', label: '资料完整' },
  { key: 'waiting', label: '等待12点' },
  { key: 'heart', label: '双方心动' },
  { key: 'chat', label: '连续聊天' },
  { key: 'unlock', label: '隐私解锁' },
]

const stageIndex = computed(() => {
  const map = { profile: 0, ready: 0, waiting: 1, heart: 2, chat: 3, unlock: 4 }
  return map[stage.value] ?? 0
})

function formatDateTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function countdown(value) {
  if (!value) return '--'
  const distance = Math.max(0, new Date(value).getTime() - now.value)
  const days = Math.floor(distance / 86400000)
  const hours = Math.floor((distance % 86400000) / 3600000)
  const minutes = Math.floor((distance % 3600000) / 60000)
  if (days) return `${days}天 ${hours}小时`
  return `${hours}小时 ${minutes}分钟`
}

async function loadStatus() {
  try {
    const { data } = await api.get('/matching/status')
    status.value = data
  } catch (error) {
    ElMessage.error(errorMessage(error, '匹配状态加载失败'))
  } finally {
    loading.value = false
  }
}

async function toggleMatching(enabled) {
  if (!status.value?.profile_complete) {
    ElMessage.warning('请先完善个人资料')
    return
  }
  saving.value = true
  try {
    const { data } = await api.patch('/matching/settings', { enabled })
    ElMessage.success(data.message)
    await loadStatus()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function chooseHeart(hearted) {
  if (!pair.value || saving.value) return
  saving.value = true
  try {
    const { data } = await api.patch(`/matching/pairs/${pair.value.id}/heart`, { hearted })
    status.value.pair = data.pair
    status.value.message = data.message
    ElMessage.success(data.message)
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function blockPartner() {
  if (!pair.value || blocking.value) return
  blocking.value = true
  try {
    const { data } = await api.post(`/matches/${pair.value.id}/block`, { reason: blockReason.value })
    blockDialog.value = false
    ElMessage.success(data.message)
    await loadStatus()
  } catch (error) {
    ElMessage.error(errorMessage(error, '屏蔽失败'))
  } finally {
    blocking.value = false
  }
}

onMounted(async () => {
  await loadStatus()
  clock = window.setInterval(() => {
    now.value = Date.now()
    if (['waiting', 'heart', 'chat'].includes(stage.value)) loadStatus()
  }, 30000)
})
onBeforeUnmount(() => window.clearInterval(clock))
</script>

<template>
  <AppShell>
    <section class="discover-page daily-page">
      <header class="page-intro daily-intro">
        <div><p class="eyebrow">每日一对一配对</p><h1>每天十二点，<span>只认真遇见一个人</span></h1></div>
        <div class="noon-stamp"><span>12:00</span><small>北京时间统一公布</small></div>
      </header>

      <div v-if="loading" class="daily-loading"><span /><span /><span /><p>正在读取今天的配对状态…</p></div>

      <div v-else class="daily-match-layout">
        <aside class="pairing-timeline">
          <p class="tiny-label">今天走到这里</p>
          <ol>
            <li v-for="(item, index) in stages" :key="item.key" :class="{ active: index === stageIndex, done: index < stageIndex }">
              <i>{{ index < stageIndex ? '✓' : index + 1 }}</i><span><b>{{ item.label }}</b><small>{{ ['完成基础信息后才能进入匹配池', '每日中午统一公布一位对象', '双方都确认后开放聊天', '保持互动，任一方沉默3天会结束', '满7天自动公开联系方式与真实照片'][index] }}</small></span>
            </li>
          </ol>
        </aside>

        <main class="daily-center">
          <section v-if="stage === 'profile'" class="gate-card">
            <div class="gate-icon">🪪</div><p class="eyebrow">匹配准入检查</p><h2>请先完善个人资料</h2>
            <p>昵称、头像、学校、年级、性别和兴趣爱好填写完整后，才能开启每日匹配；专业/院系可以选填。</p>
            <div class="missing-chips"><span v-for="item in status.missing_profile_fields" :key="item">缺少 {{ item }}</span></div>
            <button class="primary-pill" disabled>开始匹配</button>
            <router-link class="secondary-pill" to="/profile">去完善资料 →</router-link>
          </section>

          <section v-else-if="stage === 'ready'" class="daily-envelope open-invite">
            <div class="envelope-flap" /><div class="envelope-letter"><span>CampusMatch · DAILY</span><b>准备好认识<br />今天唯一的 TA 吗？</b><small>系统会综合兴趣、年龄与地域，为双方生成互为唯一的结果。</small></div>
            <div class="match-switch-row"><div><b>开始匹配</b><small>开启后加入下一次匹配池</small></div><el-switch :model-value="false" :loading="saving" size="large" @change="toggleMatching" /></div>
            <p class="release-note">下一次公布：{{ formatDateTime(status.next_release_at) }}</p>
          </section>

          <section v-else-if="stage === 'waiting'" class="daily-envelope waiting-envelope">
            <div class="envelope-seal">♥</div><div class="sealed-copy"><p class="eyebrow">已加入匹配池</p><h2>信封将在中午十二点打开</h2><p>开启期间不会提前推荐任何人。系统会在所有符合条件的用户中完成一对一互配。</p><div class="countdown-box"><small>距离下一次公布</small><b>{{ countdown(status.next_release_at) }}</b><span>{{ formatDateTime(status.next_release_at) }}</span></div></div>
            <div class="match-switch-row"><div><b>匹配已开启</b><small>关闭后不会参与下一轮</small></div><el-switch :model-value="true" :loading="saving" size="large" @change="toggleMatching" /></div>
          </section>

          <section v-else class="pair-result-card">
            <div class="result-banner"><span>✦ TODAY'S PAIR ✦</span><b>{{ pair.deep_match_used ? '今日深度配对已出' : '今日配对已出，请查看' }}</b><small>你们是今天彼此唯一的配对对象</small></div>
            <div class="pair-person">
              <div class="pair-avatar-wrap"><AvatarBubble :src="pair.partner.avatar_url" :name="pair.partner.nickname" :size="138" /><span class="score-pin">{{ Math.round(pair.match_score) }}%</span></div>
              <div class="pair-name"><h2>{{ pair.partner.nickname }} <span>{{ pair.partner.age }}</span></h2><p>{{ pair.partner.school || '学校待完善' }} · {{ pair.partner.grade }}<template v-if="pair.partner.department"> · {{ pair.partner.department }}</template></p><p v-if="pair.partner.location_province && pair.partner.location_city">📍 {{ pair.partner.location_province }} {{ pair.partner.location_city }}<template v-if="pair.partner.hometown_province && pair.partner.hometown_city"> · 🏡 {{ pair.partner.hometown_province }} {{ pair.partner.hometown_city }}</template></p></div>
              <div class="pair-bio">
                <span>个人简介</span>
                <p>{{ pair.partner.bio || '还没写简介，给彼此留一点慢慢认识的空间。' }}</p>
              </div>
              <div class="interest-cloud result-interests"><span v-for="item in pair.partner.interests" :key="item.id" :class="{ shared: pair.shared_interests.includes(item.name) }">{{ item.emoji }} {{ item.name }}</span></div>
            </div>

            <div v-if="pair.deep_match_used && pair.deep_comment" class="deep-match-comment">
              <div><b>✦ 深度适配评语</b><span class="deep-score-pills"><span>初步 {{ Math.round(pair.preliminary_score) }}</span><span>深度 {{ Math.round(pair.deep_score) }}</span><span>综合 {{ Math.round(pair.match_score) }}</span></span></div>
              <p>{{ pair.deep_comment }}</p>
            </div>

            <div v-if="pair.status === 'pending_heartbeat'" class="heart-decision">
              <div class="heart-copy"><span>💓</span><div><b>{{ pair.my_hearted ? '你的心动已送达' : '愿意继续认识 TA 吗？' }}</b><small>{{ pair.partner_hearted ? '对方已经做出心动选择' : '双方选择会分别保存' }} · {{ countdown(pair.heartbeat_expires_at) }} 后失效</small></div></div>
              <button v-if="!pair.my_hearted" class="primary-pill" :disabled="saving" @click="chooseHeart(true)">我心动了 ♥</button>
              <button v-else class="secondary-pill" :disabled="saving" @click="chooseHeart(false)">取消心动</button>
              <div class="heart-status"><span class="on">我 {{ pair.my_hearted ? '♥' : '○' }}</span><i /><span :class="{ on: pair.partner_hearted }">TA {{ pair.partner_hearted ? '♥' : '○' }}</span></div>
            </div>

            <div v-else class="chat-unlock-panel">
              <div class="unlock-head"><div><p class="eyebrow">{{ pair.privacy_unlocked ? '隐私信息已解锁' : '聊天解锁进度' }}</p><h3>{{ pair.privacy_unlocked ? '七天的认真，换来更多信任' : `已连续聊天 ${pair.chat_days} / 7 天` }}</h3></div><span>{{ pair.unlock_progress }}%</span></div>
              <el-progress :percentage="pair.unlock_progress" :show-text="false" :stroke-width="9" color="#4ECDC4" />
              <p v-if="!pair.privacy_unlocked" class="unlock-hint"><el-icon><Lock /></el-icon> 联系方式和真实照片将在 {{ formatDateTime(pair.unlock_at) }} 解锁；任一方连续3天未发消息，配对会自动结束。</p>
              <div v-else class="private-reveal">
                <div class="contact-grid"><span><small>手机号</small><b>{{ pair.private_profile.phone }}</b></span><span><small>邮箱</small><b>{{ pair.private_profile.email }}</b></span><span v-if="pair.private_profile.wechat"><small>微信号</small><b>{{ pair.private_profile.wechat }}</b></span></div>
                <div v-if="pair.private_profile.real_photos.length" class="unlocked-photos"><img v-for="photo in pair.private_profile.real_photos" :key="photo" :src="photo" alt="对方公开的真实照片" /></div>
                <p v-else class="no-private-photo">TA 暂未补充真实照片。</p>
              </div>
              <router-link class="primary-pill full" :to="`/chat/${pair.id}`"><el-icon><ChatDotRound /></el-icon> 进入聊天</router-link>
            </div>
            <button class="pair-block-link" @click="blockDialog = true">⚠ 屏蔽并结束本次配对</button>
          </section>
        </main>

        <aside class="daily-rules">
          <div><span>01</span><b>一天一次</b><p>中午12点统一公布，不再无限滑动。</p></div>
          <div><span>02</span><b>互为唯一</b><p>A 匹配到 B 时，B 的结果也一定是 A。</p></div>
          <div><span>03</span><b>隐私渐进</b><p>先看基础信息，双向心动并聊满7天才解锁隐私。</p></div>
          <div class="privacy-shield"><el-icon><Switch /></el-icon><p><b>匹配开关由你掌握</b><small>关闭后不会进入池中，也不会被推荐给他人。</small></p></div>
        </aside>
      </div>

      <el-dialog v-model="blockDialog" title="屏蔽并结束配对" width="430px" align-center>
        <p class="block-dialog-tip">如果对方疑似诈骗、骚扰或发布不良信息，可以立即结束配对。屏蔽后双方不能聊天，也不会再次匹配。</p>
        <el-radio-group v-model="blockReason" class="block-reason-list">
          <el-radio v-for="reason in ['疑似诈骗', '色情或不良信息', '血腥暴力内容', '骚扰', '其他']" :key="reason" :value="reason">{{ reason }}</el-radio>
        </el-radio-group>
        <template #footer><button class="danger-pill" :disabled="blocking" @click="blockPartner">{{ blocking ? '处理中…' : '确认屏蔽' }}</button></template>
      </el-dialog>
    </section>
  </AppShell>
</template>
