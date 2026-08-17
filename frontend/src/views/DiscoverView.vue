<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, ChatDotRound, Lock, Switch } from '@element-plus/icons-vue'

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
const currentIndex = ref(0)
const dragOffset = ref(0)
const dragging = ref(false)
let dragStartX = 0
let clock = null

const pair = computed(() => status.value?.pair || null)
const recommendations = computed(() => status.value?.recommendations || [])
const selectedRecommendation = computed(() => status.value?.selected_recommendation || null)
const currentRecommendation = computed(() => recommendations.value[currentIndex.value] || null)
const stage = computed(() => {
  if (!status.value?.profile_complete) return 'profile'
  if (pair.value?.status === 'pending_heartbeat') return 'legacy-heart'
  if (pair.value?.status === 'chatting') return 'chat'
  if (pair.value?.status === 'privacy_unlocked') return 'unlock'
  if (!status.value?.matching_enabled) return 'ready'
  if (selectedRecommendation.value) return 'selected'
  if (recommendations.value.length) return 'recommendations'
  if (status.value?.recommendations_generated) return 'empty'
  return 'waiting'
})

const stages = [
  { key: 'profile', label: '资料完整', hint: '完成基础信息后才能进入匹配池' },
  { key: 'waiting', label: '周六推荐', hint: '周六分批生成最多三位候选人' },
  { key: 'selected', label: '唯一心动', hint: '三人中只能选择一人且不可更改' },
  { key: 'chat', label: '双向确认', hint: '对方也选择你后立即开放聊天' },
  { key: 'unlock', label: '隐私解锁', hint: '聊满7天自动公开联系方式与真实照片' },
]

const stageIndex = computed(() => {
  const map = {
    profile: 0,
    ready: 0,
    waiting: 1,
    empty: 1,
    recommendations: 1,
    selected: 2,
    'legacy-heart': 2,
    chat: 3,
    unlock: 4,
  }
  return map[stage.value] ?? 0
})

function formatDateTime(value) {
  if (!value) return '--'
  return new Date(value).toLocaleString('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
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
  const previousId = currentRecommendation.value?.id
  try {
    const { data } = await api.get('/matching/status')
    status.value = data
    const preservedIndex = data.recommendations?.findIndex((item) => item.id === previousId) ?? -1
    currentIndex.value = preservedIndex >= 0 ? preservedIndex : 0
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

async function chooseRecommendation() {
  if (!currentRecommendation.value || saving.value) return
  saving.value = true
  try {
    const { data } = await api.post(`/matching/recommendations/${currentRecommendation.value.id}/heart`)
    ElMessage.success(data.message)
    await loadStatus()
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function chooseLegacyHeart(hearted) {
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

function moveCard(direction) {
  const total = recommendations.value.length
  if (total < 2) return
  currentIndex.value = (currentIndex.value + direction + total) % total
  dragOffset.value = 0
}

function beginDrag(event) {
  if (recommendations.value.length < 2 || event.button > 0) return
  dragging.value = true
  dragStartX = event.clientX
  dragOffset.value = 0
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

function dragCard(event) {
  if (!dragging.value) return
  dragOffset.value = Math.max(-150, Math.min(150, event.clientX - dragStartX))
}

function finishDrag(event) {
  if (!dragging.value) return
  dragging.value = false
  event.currentTarget.releasePointerCapture?.(event.pointerId)
  if (Math.abs(dragOffset.value) >= 65) moveCard(dragOffset.value < 0 ? 1 : -1)
  dragOffset.value = 0
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
    if (['waiting', 'recommendations', 'selected', 'legacy-heart', 'chat'].includes(stage.value)) loadStatus()
  }, 30000)
})
onBeforeUnmount(() => window.clearInterval(clock))
</script>

<template>
  <AppShell>
    <section class="discover-page daily-page weekly-page">
      <header class="page-intro daily-intro">
        <div><p class="eyebrow">每周校园心动推荐</p><h1>周六见三人，<span>只把心动留给一个人</span></h1></div>
        <div class="noon-stamp weekly-stamp"><span>SAT</span><small>北京时间分批公布</small></div>
      </header>

      <div v-if="loading" class="daily-loading"><span /><span /><span /><p>正在读取本周推荐状态…</p></div>

      <div v-else class="daily-match-layout">
        <aside class="pairing-timeline">
          <p class="tiny-label">本周走到这里</p>
          <ol>
            <li v-for="(item, index) in stages" :key="item.key" :class="{ active: index === stageIndex, done: index < stageIndex }">
              <i>{{ index < stageIndex ? '✓' : index + 1 }}</i><span><b>{{ item.label }}</b><small>{{ item.hint }}</small></span>
            </li>
          </ol>
        </aside>

        <main class="daily-center">
          <section v-if="stage === 'profile'" class="gate-card">
            <div class="gate-icon">🪪</div><p class="eyebrow">匹配准入检查</p><h2>请先完善个人资料</h2>
            <p>昵称、头像、学校、年级、性别和兴趣爱好填写完整后，才能开启每周匹配；专业/院系可以选填。</p>
            <div class="missing-chips"><span v-for="item in status.missing_profile_fields" :key="item">缺少 {{ item }}</span></div>
            <button class="primary-pill" disabled>开始匹配</button>
            <router-link class="secondary-pill" to="/profile">去完善资料 →</router-link>
          </section>

          <section v-else-if="stage === 'ready'" class="daily-envelope open-invite weekly-envelope">
            <div class="envelope-flap" /><div class="envelope-letter"><span>CampusMatch · WEEKLY</span><b>准备好在本周<br />认真认识三个人吗？</b><small>系统会综合兴趣、年龄、地域与深度问卷，为你生成独立的单向推荐列表。</small></div>
            <div class="match-switch-row"><div><b>开始匹配</b><small>开启后加入下一次周六推荐池</small></div><el-switch :model-value="false" :loading="saving" size="large" @change="toggleMatching" /></div>
            <p class="release-note">你的下一批推荐：{{ formatDateTime(status.next_release_at) }}</p>
          </section>

          <section v-else-if="stage === 'waiting'" class="daily-envelope waiting-envelope weekly-envelope">
            <div class="envelope-seal">3</div><div class="sealed-copy"><p class="eyebrow">已加入每周匹配池</p><h2>三封心动卡片正在准备</h2><p>系统按用户ID均匀分批计算，周六当天完成全部推荐，降低服务器瞬时压力。</p><div class="countdown-box"><small>距离你的推荐批次</small><b>{{ countdown(status.next_release_at) }}</b><span>{{ formatDateTime(status.next_release_at) }}</span></div></div>
            <div class="match-switch-row"><div><b>匹配已开启</b><small>关闭后本周推荐也会失效</small></div><el-switch :model-value="true" :loading="saving" size="large" @change="toggleMatching" /></div>
          </section>

          <section v-else-if="stage === 'empty'" class="gate-card weekly-empty-card">
            <div class="gate-icon">🌙</div><p class="eyebrow">本周推荐已完成</p><h2>这周暂时没有合适人选</h2>
            <p>可能是当前匹配池中的异性用户不足，或可推荐对象已经进入其他有效配对。保持开关开启，下周六会重新计算。</p>
            <div class="match-switch-row compact"><div><b>继续参加下周匹配</b><small>当前状态会实时保存</small></div><el-switch :model-value="true" :loading="saving" @change="toggleMatching" /></div>
          </section>

          <section v-else-if="stage === 'recommendations'" class="weekly-recommendation-panel">
            <div class="weekly-deck-head"><div><p class="eyebrow">本周推荐已出</p><h2>{{ recommendations.length }} 位候选，只选择 1 位</h2></div><span>{{ currentIndex + 1 }} / {{ recommendations.length }}</span></div>
            <div class="weekly-card-stack" :class="`depth-${Math.min(recommendations.length, 3)}`">
              <Transition name="recommendation-card" mode="out-in">
                <article
                  v-if="currentRecommendation"
                  :key="currentRecommendation.id"
                  class="pair-result-card weekly-candidate-card"
                  :class="{ dragging }"
                  :style="{ transform: `translateX(${dragOffset}px) rotate(${dragOffset / 35}deg)` }"
                  @pointerdown="beginDrag"
                  @pointermove="dragCard"
                  @pointerup="finishDrag"
                  @pointercancel="finishDrag"
                >
                  <div class="result-banner"><span>✦ WEEKLY PICK {{ currentRecommendation.rank }} ✦</span><b>{{ currentRecommendation.deep_match_used ? '深度适配候选' : '兴趣适配候选' }}</b><small>左右拖动或点击箭头查看其他推荐</small></div>
                  <div class="pair-person">
                    <div class="pair-avatar-wrap"><AvatarBubble :src="currentRecommendation.user.avatar_url" :name="currentRecommendation.user.nickname" :size="138" /><span class="score-pin">{{ Math.round(currentRecommendation.final_score) }}%</span></div>
                    <div class="pair-name"><h2>{{ currentRecommendation.user.nickname }} <span>{{ currentRecommendation.user.age }}</span></h2><p>{{ currentRecommendation.user.school || '学校待完善' }} · {{ currentRecommendation.user.grade }}<template v-if="currentRecommendation.user.department"> · {{ currentRecommendation.user.department }}</template></p><p v-if="currentRecommendation.user.location_province && currentRecommendation.user.location_city">📍 {{ currentRecommendation.user.location_province }} {{ currentRecommendation.user.location_city }}<template v-if="currentRecommendation.user.hometown_province && currentRecommendation.user.hometown_city"> · 🏡 {{ currentRecommendation.user.hometown_province }} {{ currentRecommendation.user.hometown_city }}</template></p></div>
                    <div v-if="currentRecommendation.user.height_cm || currentRecommendation.user.weight_kg" class="public-body-metrics"><span v-if="currentRecommendation.user.height_cm">📏 <b>{{ currentRecommendation.user.height_cm }}</b> cm</span><span v-if="currentRecommendation.user.weight_kg">⚖️ <b>{{ currentRecommendation.user.weight_kg }}</b> kg</span></div>
                    <div class="pair-bio"><span>个人简介</span><p>{{ currentRecommendation.user.bio || '还没写简介，给彼此留一点慢慢认识的空间。' }}</p></div>
                    <div class="interest-cloud result-interests"><span v-for="item in currentRecommendation.user.interests" :key="item.id" :class="{ shared: currentRecommendation.shared_interests.includes(item.name) }">{{ item.emoji }} {{ item.name }}</span></div>
                  </div>
                  <div v-if="currentRecommendation.deep_match_used && currentRecommendation.deep_comment" class="deep-match-comment weekly-deep-comment">
                    <div><b>✦ 深度适配评语</b><span class="deep-score-pills"><span>初步 {{ Math.round(currentRecommendation.preliminary_score) }}</span><span>深度 {{ Math.round(currentRecommendation.deep_score) }}</span><span>综合 {{ Math.round(currentRecommendation.final_score) }}</span></span></div>
                    <p>{{ currentRecommendation.deep_comment }}</p>
                  </div>
                </article>
              </Transition>
            </div>
            <div class="weekly-deck-controls">
              <button class="deck-arrow" :disabled="recommendations.length < 2" aria-label="查看上一位推荐" @click="moveCard(-1)"><el-icon><ArrowLeft /></el-icon></button>
              <div class="deck-dots"><button v-for="(item, index) in recommendations" :key="item.id" :class="{ active: index === currentIndex }" :aria-label="`查看第 ${index + 1} 位推荐`" @click="currentIndex = index" /></div>
              <button class="deck-arrow" :disabled="recommendations.length < 2" aria-label="查看下一位推荐" @click="moveCard(1)"><el-icon><ArrowRight /></el-icon></button>
            </div>
            <div class="weekly-heart-action"><div><span>💓</span><p><b>把本周唯一的心动送给 {{ currentRecommendation?.user.nickname }}</b><small>确认后不能撤回，也不能改选另外两人</small></p></div><button class="primary-pill" :disabled="saving" @click="chooseRecommendation">选择 TA，送出心动 ♥</button></div>
            <div class="weekly-toggle-bar"><span>不想继续参与本周推荐？关闭后当前卡片会失效。</span><el-switch :model-value="true" :loading="saving" @change="toggleMatching" /></div>
          </section>

          <section v-else-if="stage === 'selected'" class="selected-heart-card">
            <div class="selected-heart-orbit"><AvatarBubble :src="selectedRecommendation.user.avatar_url" :name="selectedRecommendation.user.nickname" :size="128" /><span>♥</span></div>
            <p class="eyebrow">本周唯一心动已送达</p><h2>你选择了 {{ selectedRecommendation.user.nickname }}</h2>
            <p>本周另外两张卡片已经自动收起。如果对方也在自己的推荐中选择了你，聊天会立即开启。</p>
            <div class="selected-summary"><span><small>综合适配</small><b>{{ Math.round(selectedRecommendation.final_score) }}%</b></span><span><small>选择状态</small><b>等待回应</b></span></div>
            <div class="match-switch-row compact"><div><b>继续等待双向心动</b><small>关闭匹配会让本次心动失效</small></div><el-switch :model-value="true" :loading="saving" @change="toggleMatching" /></div>
          </section>

          <section v-else class="pair-result-card">
            <div class="result-banner"><span>✦ MUTUAL HEART ✦</span><b>{{ pair.status === 'pending_heartbeat' ? '旧版配对等待确认' : '双向心动成功' }}</b><small>{{ pair.status === 'pending_heartbeat' ? '双方都确认后开放聊天' : '你们已经选择了彼此' }}</small></div>
            <div class="pair-person">
              <div class="pair-avatar-wrap"><AvatarBubble :src="pair.partner.avatar_url" :name="pair.partner.nickname" :size="138" /><span class="score-pin">{{ Math.round(pair.match_score) }}%</span></div>
              <div class="pair-name"><h2>{{ pair.partner.nickname }} <span>{{ pair.partner.age }}</span></h2><p>{{ pair.partner.school || '学校待完善' }} · {{ pair.partner.grade }}<template v-if="pair.partner.department"> · {{ pair.partner.department }}</template></p><p v-if="pair.partner.location_province && pair.partner.location_city">📍 {{ pair.partner.location_province }} {{ pair.partner.location_city }}<template v-if="pair.partner.hometown_province && pair.partner.hometown_city"> · 🏡 {{ pair.partner.hometown_province }} {{ pair.partner.hometown_city }}</template></p></div>
              <div v-if="pair.partner.height_cm || pair.partner.weight_kg" class="public-body-metrics"><span v-if="pair.partner.height_cm">📏 <b>{{ pair.partner.height_cm }}</b> cm</span><span v-if="pair.partner.weight_kg">⚖️ <b>{{ pair.partner.weight_kg }}</b> kg</span></div>
              <div class="pair-bio"><span>个人简介</span><p>{{ pair.partner.bio || '还没写简介，给彼此留一点慢慢认识的空间。' }}</p></div>
              <div class="interest-cloud result-interests"><span v-for="item in pair.partner.interests" :key="item.id" :class="{ shared: pair.shared_interests.includes(item.name) }">{{ item.emoji }} {{ item.name }}</span></div>
            </div>

            <div v-if="pair.deep_match_used && pair.deep_comment" class="deep-match-comment"><div><b>✦ 深度适配评语</b><span class="deep-score-pills"><span>初步 {{ Math.round(pair.preliminary_score) }}</span><span>深度 {{ Math.round(pair.deep_score) }}</span><span>综合 {{ Math.round(pair.match_score) }}</span></span></div><p>{{ pair.deep_comment }}</p></div>

            <div v-if="pair.status === 'pending_heartbeat'" class="heart-decision">
              <div class="heart-copy"><span>💓</span><div><b>{{ pair.my_hearted ? '你的心动已送达' : '愿意继续认识 TA 吗？' }}</b><small>{{ pair.partner_hearted ? '对方已经做出心动选择' : '这是升级前生成的旧版配对' }} · {{ countdown(pair.heartbeat_expires_at) }} 后失效</small></div></div>
              <button v-if="!pair.my_hearted" class="primary-pill" :disabled="saving" @click="chooseLegacyHeart(true)">我心动了 ♥</button>
              <button v-else class="secondary-pill" :disabled="saving" @click="chooseLegacyHeart(false)">取消心动</button>
              <div class="heart-status"><span class="on">我 {{ pair.my_hearted ? '♥' : '○' }}</span><i /><span :class="{ on: pair.partner_hearted }">TA {{ pair.partner_hearted ? '♥' : '○' }}</span></div>
            </div>

            <div v-else class="chat-unlock-panel">
              <div class="unlock-head"><div><p class="eyebrow">{{ pair.privacy_unlocked ? '隐私信息已解锁' : '聊天解锁进度' }}</p><h3>{{ pair.privacy_unlocked ? '七天的认真，换来更多信任' : `已连续聊天 ${pair.chat_days} / 7 天` }}</h3></div><span>{{ pair.unlock_progress }}%</span></div>
              <el-progress :percentage="pair.unlock_progress" :show-text="false" :stroke-width="9" color="#4ECDC4" />
              <p v-if="!pair.privacy_unlocked" class="unlock-hint"><el-icon><Lock /></el-icon> 联系方式和真实照片将在 {{ formatDateTime(pair.unlock_at) }} 解锁；任一方连续3天未发消息，配对会自动结束。</p>
              <div v-else class="private-reveal"><div class="contact-grid"><span><small>手机号</small><b>{{ pair.private_profile.phone }}</b></span><span><small>邮箱</small><b>{{ pair.private_profile.email }}</b></span><span v-if="pair.private_profile.wechat"><small>微信号</small><b>{{ pair.private_profile.wechat }}</b></span></div><div v-if="pair.private_profile.real_photos.length" class="unlocked-photos"><img v-for="photo in pair.private_profile.real_photos" :key="photo" :src="photo" alt="对方公开的真实照片" /></div><p v-else class="no-private-photo">TA 暂未补充真实照片。</p></div>
              <router-link class="primary-pill full" :to="`/chat/${pair.id}`"><el-icon><ChatDotRound /></el-icon> 进入聊天</router-link>
            </div>
            <button class="pair-block-link" @click="blockDialog = true">⚠ 屏蔽并结束本次配对</button>
          </section>
        </main>

        <aside class="daily-rules">
          <div><span>01</span><b>每周一次</b><p>固定周六分批计算，推荐有效期为一周。</p></div>
          <div><span>02</span><b>三选一</b><p>最多查看三位单向推荐，只能选择其中一位。</p></div>
          <div><span>03</span><b>双向才配对</b><p>只有彼此都选择对方，才会创建聊天关系。</p></div>
          <div class="privacy-shield"><el-icon><Switch /></el-icon><p><b>隐私渐进公开</b><small>推荐只显示基础资料，双向心动并聊满7天才解锁隐私。</small></p></div>
        </aside>
      </div>

      <el-dialog v-model="blockDialog" title="屏蔽并结束配对" width="430px" align-center>
        <p class="block-dialog-tip">如果对方疑似诈骗、骚扰或发布不良信息，可以立即结束配对。屏蔽后双方不能聊天，也不会再次匹配。</p>
        <el-radio-group v-model="blockReason" class="block-reason-list"><el-radio v-for="reason in ['疑似诈骗', '色情或不良信息', '血腥暴力内容', '骚扰', '其他']" :key="reason" :value="reason">{{ reason }}</el-radio></el-radio-group>
        <template #footer><button class="danger-pill" :disabled="blocking" @click="blockPartner">{{ blocking ? '处理中…' : '确认屏蔽' }}</button></template>
      </el-dialog>
    </section>
  </AppShell>
</template>
