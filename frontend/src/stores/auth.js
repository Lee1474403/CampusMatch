import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '../api/client'
import { clearAuthTokens, getAccessToken, saveAuthTokens } from '../utils/authStorage'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(false)
  const accessToken = ref(getAccessToken())
  const isAuthenticated = computed(() => Boolean(accessToken.value))

  function saveTokens(tokens) {
    saveAuthTokens(tokens)
    accessToken.value = tokens.access_token
  }

  async function login(payload) {
    const { data } = await api.post('/auth/login', payload)
    saveTokens(data)
    await fetchMe()
  }

  async function register(payload) {
    const { data } = await api.post('/auth/register', payload)
    saveTokens(data)
    await fetchMe()
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
    if (isAuthenticated.value && !user.value) {
      try {
        await fetchMe()
      } catch {
        clearSession()
      }
    }
  }

  function clearSession() {
    clearAuthTokens()
    accessToken.value = null
    user.value = null
  }

  async function logout() {
    try {
      await api.post('/auth/logout')
    } finally {
      clearSession()
    }
  }

  return { user, loading, isAuthenticated, login, register, fetchMe, restoreSession, logout, clearSession }
})
