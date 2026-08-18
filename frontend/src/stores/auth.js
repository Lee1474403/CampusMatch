import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import { clearLegacyAuthTokens } from '../utils/authStorage'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(false)
  const initialized = ref(false)
  const isAuthenticated = computed(() => Boolean(user.value))

  async function login(payload) {
    await api.post('/auth/login', payload)
    return fetchMe()
  }

  async function register(payload) {
    const { data } = await api.post('/auth/register', payload)
    return data
  }

  async function fetchMe() {
    loading.value = true
    try {
      const { data } = await api.get('/profile/me')
      user.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function restoreSession() {
    if (initialized.value) return isAuthenticated.value
    try {
      await fetchMe()
    } catch {
      clearSession()
    } finally {
      initialized.value = true
    }
    return isAuthenticated.value
  }

  function clearSession() {
    clearLegacyAuthTokens()
    user.value = null
  }

  async function logout() {
    try {
      await api.post('/auth/logout')
    } finally {
      clearSession()
      initialized.value = true
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('campusmatch:session-expired', () => {
      clearSession()
      initialized.value = true
    })
  }

  return {
    user,
    loading,
    initialized,
    isAuthenticated,
    login,
    register,
    fetchMe,
    restoreSession,
    logout,
    clearSession,
  }
})
