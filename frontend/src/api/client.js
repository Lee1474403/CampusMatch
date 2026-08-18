import axios from 'axios'
import { clearLegacyAuthTokens } from '../utils/authStorage'

export { errorMessage } from '../utils/errors'

export const api = axios.create({
  baseURL: '/api',
  timeout: 12000,
  withCredentials: true,
})

let refreshPromise = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const url = String(original?.url || '')
    const cannotRefresh = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/verify-email'].some((path) => url.includes(path))
    if (error.response?.status !== 401 || original?._retried || cannotRefresh) {
      return Promise.reject(error)
    }

    original._retried = true
    try {
      refreshPromise ||= axios.post('/api/auth/refresh', {}, { withCredentials: true })
      await refreshPromise
      return api(original)
    } catch (refreshError) {
      clearLegacyAuthTokens()
      window.dispatchEvent(new CustomEvent('campusmatch:session-expired'))
      if (!['/auth', '/verify-email'].includes(window.location.pathname)) window.location.assign('/auth')
      return Promise.reject(refreshError)
    } finally {
      refreshPromise = null
    }
  },
)
