import axios from 'axios'
import { clearAuthTokens, getAccessToken, getRefreshToken, saveAuthTokens } from '../utils/authStorage'

export { errorMessage } from '../utils/errors'

export const api = axios.create({
  baseURL: '/api',
  timeout: 12000,
})

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshPromise = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const refreshToken = getRefreshToken()
    if (error.response?.status !== 401 || original?._retried || !refreshToken) {
      return Promise.reject(error)
    }
    original._retried = true
    try {
      refreshPromise ||= axios.post('/api/auth/refresh', { refresh_token: refreshToken })
      const { data } = await refreshPromise
      saveAuthTokens(data)
      original.headers.Authorization = `Bearer ${data.access_token}`
      return api(original)
    } catch (refreshError) {
      clearAuthTokens()
      if (window.location.pathname !== '/auth') window.location.assign('/auth')
      return Promise.reject(refreshError)
    } finally {
      refreshPromise = null
    }
  },
)
