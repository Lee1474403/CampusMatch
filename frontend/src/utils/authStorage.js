const ACCESS_TOKEN_KEY = 'campusmatch_access'
const REFRESH_TOKEN_KEY = 'campusmatch_refresh'

function migrateLegacyTokens() {
  if (typeof window === 'undefined') return

  for (const key of [ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY]) {
    const legacyValue = window.localStorage.getItem(key)
    if (!window.sessionStorage.getItem(key) && legacyValue) {
      window.sessionStorage.setItem(key, legacyValue)
    }
    window.localStorage.removeItem(key)
  }
}

migrateLegacyTokens()

export function getAccessToken() {
  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY)
}

export function getRefreshToken() {
  return window.sessionStorage.getItem(REFRESH_TOKEN_KEY)
}

export function saveAuthTokens(tokens) {
  window.sessionStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token)
  window.sessionStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token)
}

export function clearAuthTokens() {
  window.sessionStorage.removeItem(ACCESS_TOKEN_KEY)
  window.sessionStorage.removeItem(REFRESH_TOKEN_KEY)
}
