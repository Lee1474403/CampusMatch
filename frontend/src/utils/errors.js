export function errorMessage(error, fallback = '操作没有完成，请稍后重试') {
  const detail = error.response?.data?.detail
  if (Array.isArray(detail)) {
    const item = detail[0]
    const field = [...(item?.loc || [])].reverse().find((part) => typeof part === 'string' && part !== 'body')
    const labels = {
      account: '账号', phone: '手机号', email: '邮箱', password: '密码', nickname: '昵称', real_name: '真实姓名',
      birth_date: '生日', school: '学校', department: '专业/院系', grade: '年级', location_province: '所在省份', location_city: '所在城市',
      hometown_province: '家乡省份', hometown_city: '家乡城市',
      bio: '个人简介', wechat: '微信号', content: '消息内容', interest_ids: '兴趣标签',
    }
    const label = labels[field] || '填写内容'
    if (field === 'location_province') return '请选择所在省份'
    if (field === 'location_city') return '请选择所在城市'
    if (field === 'hometown_province') return '请选择家乡省份'
    if (field === 'hometown_city') return '请选择家乡城市'
    if (item?.type === 'missing') return `请填写${label}`
    if (item?.type === 'string_too_short') return `${label}不能为空或长度不足`
    if (item?.type === 'string_too_long') return `${label}长度超过限制`
    if (item?.type === 'value_error') {
      if (field === 'email') return '请输入正确的邮箱地址'
      return item.msg?.replace(/^Value error, /, '') || `${label}格式不正确`
    }
    return `${label}格式不正确`
  }
  return detail || fallback
}
