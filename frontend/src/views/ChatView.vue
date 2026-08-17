<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Back, Promotion, Search } from '@element-plus/icons-vue'

import { api, errorMessage } from '../api/client'
import AppShell from '../components/AppShell.vue'
import AvatarBubble from '../components/AvatarBubble.vue'
import { useAuthStore } from '../stores/auth'
import { getAccessToken } from '../utils/authStorage'
import { formatChinaDate, formatChinaShortDate, formatChinaTime, isTodayInChina, parseApiDate } from '../utils/dateTime'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const matches = ref([])
const messages = ref([])
const selectedId = ref(null)
const draft = ref('')
const search = ref('')
const loading = ref(true)
const messageList = ref(null)
const blockDialog = ref(false)
const blockReason = ref('疑似诈骗')
const blocking = ref(false)
const pendingDraft = ref('')
let socket = null
let reconnectTimer = null
let intentionalClose = false

const selected = computed(() => matches.value.find((item) => item.id === selectedId.value) || null)
const filteredMatches = computed(() => {
  const query = search.value.trim().toLowerCase()
  return query ? matches.value.filter((item) => item.user.nickname.toLowerCase().includes(query)) : matches.value
})

function timeLabel(value) {
  const date = parseApiDate(value)
  if (!date) return ''
  return isTodayInChina(date) ? formatChinaTime(date) : formatChinaShortDate(date)
}

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

async function loadMatches() {
  const { data } = await api.get('/matches')
  matches.value = data
  const routeId = Number(route.params.matchId)
  if (routeId && data.some((item) => item.id === routeId)) selectedId.value = routeId
  else if (!selectedId.value && data.length) selectedId.value = data[0].id
  else if (selectedId.value && !data.some((item) => item.id === selectedId.value)) selectedId.value = data[0]?.id || null
}

async function selectMatch(id) {
  selectedId.value = id
  router.replace(`/chat/${id}`)
}

async function loadMessages(matchId) {
  if (!matchId) return
  loading.value = true
  try {
    const { data } = await api.get(`/matches/${matchId}/messages`)
    messages.value = data
    const item = matches.value.find((match) => match.id === matchId)
    if (item) item.unread_count = 0
    await scrollToBottom()
  } catch (error) {
    ElMessage.error(errorMessage(error, '聊天记录加载失败'))
  } finally {
    loading.value = false
  }
}

function connectSocket(matchId) {
  intentionalClose = true
  if (socket) socket.close()
  clearTimeout(reconnectTimer)
  intentionalClose = false
  if (!matchId) return
  const token = getAccessToken()
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const configured = import.meta.env.VITE_WS_URL
  const url = configured
    ? `${configured.replace(/\/$/, '')}/api/ws/chat/${matchId}?token=${encodeURIComponent(token)}`
    : `${protocol}//${window.location.host}/api/ws/chat/${matchId}?token=${encodeURIComponent(token)}`
  socket = new WebSocket(url)
  socket.onmessage = async (event) => {
    const payload = JSON.parse(event.data)
    if (payload.type === 'message' && payload.data.match_id === selectedId.value) {
      if (payload.data.sender_id === auth.user?.id) pendingDraft.value = ''
      if (!messages.value.some((item) => item.id === payload.data.id)) messages.value.push(payload.data)
      const match = matches.value.find((item) => item.id === selectedId.value)
      if (match) {
        match.last_message = payload.data.content
        match.last_message_at = payload.data.sent_at
      }
      await scrollToBottom()
    }
    if (payload.type === 'presence') {
      const match = matches.value.find((item) => item.user.id === payload.user_id)
      if (match) match.online = payload.online
    }
    if (payload.type === 'read' && payload.match_id === selectedId.value) {
      messages.value.forEach((item) => {
        if (item.sender_id === auth.user?.id) item.is_read = true
      })
    }
    if (payload.type === 'pair_dissolved') {
      ElMessage.warning(payload.message)
      loadMatches()
    }
    if (payload.type === 'pair_status') loadMatches()
    if (payload.type === 'error') {
      if (pendingDraft.value && !draft.value.trim()) draft.value = pendingDraft.value
      pendingDraft.value = ''
      ElMessage.error(payload.message || '消息发送失败')
    }
  }
  socket.onclose = (event) => {
    if (event.code === 4410) {
      loadMatches()
      return
    }
    if (!intentionalClose && selectedId.value === matchId) reconnectTimer = setTimeout(() => connectSocket(matchId), 1800)
  }
}

async function sendMessage() {
  const content = draft.value.trim()
  if (!content || !selectedId.value) return
  draft.value = ''
  if (socket?.readyState === WebSocket.OPEN) {
    pendingDraft.value = content
    socket.send(JSON.stringify({ type: 'message', content }))
    return
  }
  try {
    const { data } = await api.post(`/matches/${selectedId.value}/messages`, { content })
    if (!messages.value.some((item) => item.id === data.id)) messages.value.push(data)
    await scrollToBottom()
  } catch (error) {
    draft.value = content
    ElMessage.error(errorMessage(error, '消息发送失败'))
  }
}

async function blockPartner() {
  if (!selectedId.value || blocking.value) return
  blocking.value = true
  try {
    const { data } = await api.post(`/matches/${selectedId.value}/block`, { reason: blockReason.value })
    blockDialog.value = false
    ElMessage.success(data.message)
    intentionalClose = true
    socket?.close()
    socket = null
    await loadMatches()
    if (!matches.value.length) router.replace('/chat')
  } catch (error) {
    ElMessage.error(errorMessage(error, '屏蔽失败'))
  } finally {
    blocking.value = false
  }
}

function addEmoji(emoji) {
  draft.value += emoji
}

watch(selectedId, async (id) => {
  if (!id) {
    intentionalClose = true
    socket?.close()
    socket = null
    return
  }
  await loadMessages(id)
  connectSocket(id)
})

watch(() => route.params.matchId, (id) => {
  const numeric = Number(id)
  if (numeric && numeric !== selectedId.value) selectedId.value = numeric
})

onMounted(async () => {
  try {
    if (!auth.user) await auth.fetchMe()
    await loadMatches()
  } catch (error) {
    ElMessage.error(errorMessage(error, '配对列表加载失败'))
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  intentionalClose = true
  clearTimeout(reconnectTimer)
  socket?.close()
})
</script>

<template>
  <AppShell>
    <section class="chat-page">
      <div class="chat-window" :class="{ 'has-selection': selected }">
        <aside class="conversation-sidebar">
          <div class="conversation-head"><div><p class="eyebrow">双向心动</p><h1>聊天</h1></div><span>{{ matches.length }} 位</span></div>
          <el-input v-model="search" class="chat-search" :prefix-icon="Search" placeholder="搜索配对昵称" clearable />
          <div class="conversation-list">
            <button v-for="item in filteredMatches" :key="item.id" :class="{ active: item.id === selectedId }" @click="selectMatch(item.id)">
              <AvatarBubble :src="item.user.avatar_url" :name="item.user.nickname" :size="52" :online="item.online" />
              <span class="conversation-copy"><span><b>{{ item.user.nickname }}</b><small>{{ timeLabel(item.last_message_at || item.matched_at) }}</small></span><span><em>{{ item.last_message || '已经配对成功，打个招呼吧 👋' }}</em><i v-if="item.unread_count">{{ item.unread_count }}</i></span></span>
            </button>
            <div v-if="!filteredMatches.length" class="empty-conversations"><span>💌</span><b>{{ matches.length ? '没有找到这个昵称' : '还没有开放聊天的配对' }}</b><p>{{ matches.length ? '换个关键词试试。' : '先去遇见页开启每周匹配，并等待双方都选择彼此。' }}</p><router-link v-if="!matches.length" to="/discover">查看每周推荐</router-link></div>
          </div>
        </aside>

        <main v-if="selected" class="message-panel">
          <header class="message-head">
            <button class="back-to-list" @click="selectedId = null; router.push('/chat')"><el-icon><Back /></el-icon></button>
            <AvatarBubble :src="selected.user.avatar_url" :name="selected.user.nickname" :size="44" :online="selected.online" />
            <div><h2>{{ selected.user.nickname }}</h2><p :class="{ online: selected.online }">{{ selected.privacy_unlocked ? '隐私已解锁 · ' : `聊天进度 ${selected.chat_days}/7 天 · ` }}{{ selected.online ? '在线' : '离线' }}</p></div>
            <div class="message-actions">
              <el-popover placement="bottom-end" :width="290" trigger="click">
                <template #reference><button class="profile-more">了解 TA</button></template>
                <div class="partner-card"><AvatarBubble :src="selected.user.avatar_url" :name="selected.user.nickname" :size="70" /><h3>{{ selected.user.nickname }} · {{ selected.user.age }}</h3><p>{{ selected.user.school || '学校待完善' }} · {{ selected.user.grade }}<template v-if="selected.user.department"> · {{ selected.user.department }}</template></p><p v-if="selected.user.location_province && selected.user.location_city">📍 现居 {{ selected.user.location_province }} {{ selected.user.location_city }}</p><p v-if="selected.user.hometown_province && selected.user.hometown_city">🏡 家乡 {{ selected.user.hometown_province }} {{ selected.user.hometown_city }}</p><p>{{ selected.user.bio }}</p><div><span v-for="tag in selected.user.interests" :key="tag.id">{{ tag.emoji }} {{ tag.name }}</span></div><div v-if="selected.privacy_unlocked" class="chat-private-info"><p><b>手机号</b>{{ selected.private_profile.phone }}</p><p><b>邮箱</b>{{ selected.private_profile.email }}</p><p v-if="selected.private_profile.wechat"><b>微信</b>{{ selected.private_profile.wechat }}</p><div v-if="selected.private_profile.real_photos.length" class="chat-private-photos"><img v-for="photo in selected.private_profile.real_photos" :key="photo" :src="photo" alt="对方公开的真实照片" /></div></div><p v-else class="chat-private-lock">🔒 连续聊天满7天后解锁联系方式与真实照片</p></div>
              </el-popover>
              <button class="chat-block-button" @click="blockDialog = true">屏蔽</button>
            </div>
          </header>

          <div ref="messageList" class="message-list">
            <div class="chat-progress-strip"><span>{{ selected.privacy_unlocked ? '🔓' : '🔐' }}</span><div><b>{{ selected.privacy_unlocked ? '隐私信息已解锁' : `隐私解锁进度 ${selected.unlock_progress}%` }}</b><small>{{ selected.privacy_unlocked ? '双方已连续聊天满7天' : `已聊 ${selected.chat_days}/7 天 · 任一方3天未发消息会自动解除` }}</small></div><el-progress :percentage="selected.unlock_progress" :show-text="false" :stroke-width="6" color="#4ECDC4" /></div>
            <div v-if="selected.deep_match_used && selected.deep_comment" class="chat-deep-comment"><b>✦ 深度匹配给你们的开场提示 · 综合 {{ Math.round(selected.match_score) }} 分</b><p>{{ selected.deep_comment }}</p></div>
            <div class="match-start"><span>💞</span><b>你们在 {{ formatChinaDate(selected.matched_at) }} 完成双向心动</b><p>从第一条消息开始计算7天解锁时间。</p></div>
            <div v-for="message in messages" :key="message.id" class="message-row" :class="{ mine: message.sender_id === auth.user?.id }">
              <AvatarBubble v-if="message.sender_id !== auth.user?.id" :src="selected.user.avatar_url" :name="selected.user.nickname" :size="34" />
              <div><p>{{ message.content }}</p><span>{{ timeLabel(message.sent_at) }}<i v-if="message.sender_id === auth.user?.id"> · {{ message.is_read ? '已读' : '未读' }}</i></span></div>
            </div>
          </div>

          <footer class="message-composer">
            <p class="chat-safety-hint">🛡️ 系统会拦截色情、血腥暴力及转账诈骗等风险内容</p>
            <div class="emoji-row"><button v-for="emoji in ['😊', '👋', '🎉', '❤️', '哈哈']" :key="emoji" @click="addEmoji(emoji)">{{ emoji }}</button></div>
            <div class="compose-row"><textarea v-model="draft" maxlength="1000" rows="1" placeholder="说点什么…（Enter 发送，Shift+Enter 换行）" @keydown.enter.exact.prevent="sendMessage" /><button :disabled="!draft.trim()" aria-label="发送消息" @click="sendMessage"><el-icon><Promotion /></el-icon></button></div>
          </footer>
        </main>

        <main v-else class="chat-placeholder"><div class="postcard-stack"><span>💬</span></div><h2>选一个人，继续聊聊</h2><p>只有互相喜欢的人才能进入这里。聊天记录会安全地为你保存。</p></main>
      </div>
    </section>

    <el-dialog v-model="blockDialog" title="屏蔽并结束配对" width="430px" align-center>
      <p class="block-dialog-tip">屏蔽后双方将无法继续聊天，你们也不会再次被系统匹配。你可以稍后在个人中心解除屏蔽。</p>
      <el-radio-group v-model="blockReason" class="block-reason-list">
        <el-radio v-for="reason in ['疑似诈骗', '色情或不良信息', '血腥暴力内容', '骚扰', '其他']" :key="reason" :value="reason">{{ reason }}</el-radio>
      </el-radio-group>
      <template #footer><button class="danger-pill" :disabled="blocking" @click="blockPartner">{{ blocking ? '处理中…' : '确认屏蔽' }}</button></template>
    </el-dialog>
  </AppShell>
</template>
