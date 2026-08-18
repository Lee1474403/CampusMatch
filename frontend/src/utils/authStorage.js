const LEGACY_TOKEN_KEYS = ['campusmatch_access', 'campusmatch_refresh']

export function clearLegacyAuthTokens() {
  if (typeof window === 'undefined') return
  for (const key of LEGACY_TOKEN_KEYS) {
    window.localStorage.removeItem(key)
    window.sessionStorage.removeItem(key)
  }
}

// One-time cleanup for users upgrading from the JavaScript-readable token version.
clearLegacyAuthTokens()
