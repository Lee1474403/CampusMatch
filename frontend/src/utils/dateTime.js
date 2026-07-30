const HAS_TIMEZONE = /(Z|[+-]\d{2}:?\d{2})$/i

export function parseApiDate(value) {
  if (!value) return null
  const normalized = typeof value === 'string' && !HAS_TIMEZONE.test(value) ? `${value}Z` : value
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function chinaDateParts(date) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date).reduce((parts, item) => {
    if (item.type !== 'literal') parts[item.type] = item.value
    return parts
  }, {})
}

export function isTodayInChina(date, now = new Date()) {
  if (!date) return false
  const left = chinaDateParts(date)
  const right = chinaDateParts(now)
  return left.year === right.year && left.month === right.month && left.day === right.day
}

export function formatChinaTime(value) {
  const date = value instanceof Date ? value : parseApiDate(value)
  if (!date) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatChinaShortDate(value) {
  const date = value instanceof Date ? value : parseApiDate(value)
  if (!date) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: 'numeric',
    day: 'numeric',
  }).format(date)
}

export function formatChinaDate(value) {
  const date = value instanceof Date ? value : parseApiDate(value)
  if (!date) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  }).format(date)
}
