<script setup>
import { Bell, ChatDotRound, Compass, Tickets, User } from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { api } from '../api/client'
import { useAuthStore } from '../stores/auth'
import AvatarBubble from './AvatarBubble.vue'

const router = useRouter()
const auth = useAuthStore()
const notifications = ref([])
const unread = ref(0)
const popoverOpen = ref(false)

const nav = [
  { to: '/discover', label: '遇见', icon: Compass },
  { to: '/questionnaire', label: '深度匹配', icon: Tickets },
  { to: '/chat', label: '聊天', icon: ChatDotRound },
  { to: '/profile', label: '我的', icon: User },
]

const userName = computed(() => auth.user?.nickname || '同学')

async function loadNotifications() {
  try {
    const { data } = await api.get('/notifications')
    notifications.value = data.items
    unread.value = data.unread_count
  } catch {
    // The shell stays usable when notifications are temporarily unavailable.
  }
}

async function openNotification(item) {
  if (!item.is_read) {
    await api.patch(`/notifications/${item.id}/read`)
    item.is_read = true
    unread.value = Math.max(0, unread.value - 1)
  }
  popoverOpen.value = false
  if (item.related_id) {
    const chatTypes = ['message', 'match', 'mutual_heart', 'privacy_unlocked']
    router.push(chatTypes.includes(item.type) ? `/chat/${item.related_id}` : '/discover')
  }
}

async function markAllRead() {
  await api.patch('/notifications/read-all')
  notifications.value.forEach((item) => { item.is_read = true })
  unread.value = 0
  ElMessage.success('通知都看过啦')
}

onMounted(async () => {
  if (!auth.user) await auth.restoreSession()
  await loadNotifications()
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <router-link class="brand" to="/discover" aria-label="CampusMatch 首页">
        <span class="brand-mark">C<span>♥</span></span>
        <span class="brand-copy"><b>CampusMatch</b><small>遇见同频的你</small></span>
      </router-link>

      <nav class="desktop-nav" aria-label="主导航">
        <router-link v-for="item in nav" :key="item.to" :to="item.to">
          <el-icon><component :is="item.icon" /></el-icon>
          {{ item.label }}
        </router-link>
      </nav>

      <div class="topbar-actions">
        <el-popover v-model:visible="popoverOpen" placement="bottom-end" :width="350" trigger="click" popper-class="notification-popover">
          <template #reference>
            <button class="icon-button" aria-label="查看通知" @click="loadNotifications">
              <el-badge :value="unread" :hidden="!unread" :max="99"><el-icon><Bell /></el-icon></el-badge>
            </button>
          </template>
          <div class="notification-head">
            <div><b>新鲜事</b><small>{{ unread ? `${unread} 条还没看` : '都看过啦' }}</small></div>
            <button v-if="unread" @click="markAllRead">全部已读</button>
          </div>
          <div class="notification-list">
            <button v-for="item in notifications" :key="item.id" :class="{ unread: !item.is_read }" @click="openNotification(item)">
              <span>{{ ['daily_pair', 'match'].includes(item.type) ? '💌' : item.type === 'mutual_heart' ? '💞' : item.type === 'privacy_unlocked' ? '🔓' : item.type === 'pair_dissolved' ? '🌙' : '💬' }}</span>
              <span><b>{{ item.content }}</b><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</small></span>
            </button>
            <div v-if="!notifications.length" class="empty-mini">暂时没有新通知，去遇见页看看吧。</div>
          </div>
        </el-popover>
        <router-link class="profile-chip" to="/profile">
          <AvatarBubble :src="auth.user?.avatar_url" :name="userName" :size="38" />
          <span>{{ userName }}</span>
        </router-link>
      </div>
    </header>

    <main class="shell-content"><slot /></main>

    <nav class="mobile-nav" aria-label="移动端主导航">
      <router-link v-for="item in nav" :key="item.to" :to="item.to">
        <el-icon><component :is="item.icon" /></el-icon><span>{{ item.label }}</span>
      </router-link>
    </nav>
  </div>
</template>
