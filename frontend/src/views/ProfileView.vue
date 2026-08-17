<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Camera, Lock, Search, SwitchButton } from '@element-plus/icons-vue'

import { api, errorMessage } from '../api/client'
import AppShell from '../components/AppShell.vue'
import AvatarBubble from '../components/AvatarBubble.vue'
import AvatarCropper from '../components/AvatarCropper.vue'
import { PROVINCE_OPTIONS, cityLabel, cityOptionsFor, isSingleLevelRegion } from '../data/chinaRegions'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()
const interests = ref([])
const questionnaireStatus = ref(null)
const interestSearch = ref('')
const activeInterestCategory = ref('')
const saving = ref(false)
const uploading = ref(false)
const cropperVisible = ref(false)
const cropFile = ref(null)
const uploadingReal = ref(false)
const passwordDialog = ref(false)
const blockedUsers = ref([])
const passwordForm = reactive({ current_password: '', new_password: '' })
const form = reactive({
  phone: '', email: '', nickname: '', real_name: '', wechat: '', birth_date: '', department: '', grade: '',
  school: '', height_cm: null, weight_kg: null,
  location_province: '', location_city: '', hometown_province: '', hometown_city: '', bio: '', interest_ids: [],
})

const bioLength = computed(() => form.bio?.length || 0)
const cityOptions = computed(() => cityOptionsFor(form.location_province))
const singleLevelLocation = computed(() => isSingleLevelRegion(form.location_province))
const hometownCityOptions = computed(() => cityOptionsFor(form.hometown_province))
const singleLevelHometown = computed(() => isSingleLevelRegion(form.hometown_province))
const interestCategoryMeta = {
  运动健身: { emoji: '🏅', description: '找到能一起挥拍、奔跑或训练的人' },
  音乐: { emoji: '🎧', description: '从曲风到乐器，把耳机里的世界说清楚' },
  阅读: { emoji: '📚', description: '你会为哪一种故事或思想停下来' },
  游戏: { emoji: '🎮', description: '组队偏好越具体，越容易遇到合拍队友' },
  动漫影视: { emoji: '🎬', description: '从国漫日漫到电影类型，找到同频片单' },
  创作艺术: { emoji: '🎨', description: '记录、表达和创造，也是认识你的方式' },
  户外旅行: { emoji: '🧭', description: '喜欢怎样出发，也许比目的地更重要' },
  生活方式: { emoji: '🌿', description: '日常的小偏好，往往最适合开启聊天' },
  科技校园: { emoji: '💡', description: '学习、技术和校园参与中的共同话题' },
}

const interestCategories = computed(() => {
  const names = []
  for (const item of interests.value) {
    const category = item.category || '其他'
    if (!names.includes(category)) names.push(category)
  }
  return names
})

const selectedInterests = computed(() => {
  const selected = new Set(form.interest_ids)
  return interests.value.filter((item) => selected.has(item.id))
})

const visibleInterests = computed(() => {
  const query = interestSearch.value.trim().toLowerCase()
  if (query) {
    return interests.value.filter((item) => `${item.category} ${item.name}`.toLowerCase().includes(query))
  }
  return interests.value.filter((item) => (item.category || '其他') === activeInterestCategory.value)
})

const activeCategoryInfo = computed(() => {
  if (interestSearch.value.trim()) return { emoji: '🔎', description: `找到 ${visibleInterests.value.length} 个相关标签` }
  return interestCategoryMeta[activeInterestCategory.value] || { emoji: '✨', description: '选择最能代表你的具体兴趣' }
})

function categorySelectedCount(category) {
  return selectedInterests.value.filter((item) => (item.category || '其他') === category).length
}

function selectInterestCategory(category) {
  activeInterestCategory.value = category
  interestSearch.value = ''
}

function removeInterest(interestId) {
  form.interest_ids = form.interest_ids.filter((id) => id !== interestId)
}

watch(() => form.location_province, (province, previousProvince) => {
  if (!province) {
    form.location_city = ''
    return
  }
  if (isSingleLevelRegion(province)) {
    form.location_city = province
    return
  }
  if (province !== previousProvince && !cityOptionsFor(province).includes(form.location_city)) {
    form.location_city = ''
  }
})

watch(() => form.hometown_province, (province, previousProvince) => {
  if (!province) {
    form.hometown_city = ''
    return
  }
  if (isSingleLevelRegion(province)) {
    form.hometown_city = province
    return
  }
  if (province !== previousProvince && !cityOptionsFor(province).includes(form.hometown_city)) {
    form.hometown_city = ''
  }
})

function fillForm(user) {
  Object.assign(form, {
    phone: user.phone || '', email: user.email || '', nickname: user.nickname || '', real_name: user.real_name || '', wechat: user.wechat || '',
    birth_date: user.birth_date || '', school: user.school || '', department: user.department || '', grade: user.grade || '',
    height_cm: user.height_cm ?? null, weight_kg: user.weight_kg ?? null,
    location_province: user.location_province || '', location_city: user.location_city || '',
    hometown_province: user.hometown_province || '', hometown_city: user.hometown_city || '', bio: user.bio || '',
    interest_ids: user.interests?.map((item) => item.id) || [],
  })
}

async function load() {
  const [user, tags, questionnaire, blocks] = await Promise.all([
    auth.fetchMe(),
    api.get('/interests'),
    api.get('/questionnaire/status'),
    api.get('/blocks'),
  ])
  fillForm(user)
  interests.value = tags.data
  questionnaireStatus.value = questionnaire.data
  blockedUsers.value = blocks.data
  if (!interestCategories.value.includes(activeInterestCategory.value)) {
    activeInterestCategory.value = interestCategories.value[0] || ''
  }
}

function blockedDate(value) {
  return value ? new Date(value).toLocaleDateString('zh-CN', { timeZone: 'Asia/Shanghai' }) : ''
}

async function unblockUser(item) {
  try {
    await ElMessageBox.confirm(
      `解除对 ${item.user.nickname} 的屏蔽后，未来可能重新匹配，但已经结束的配对不会恢复。`,
      '解除屏蔽',
      { confirmButtonText: '确认解除', cancelButtonText: '取消', type: 'warning' },
    )
    const { data } = await api.delete(`/blocks/${item.user.id}`)
    blockedUsers.value = blockedUsers.value.filter((block) => block.id !== item.id)
    ElMessage.success(data.message)
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    ElMessage.error(errorMessage(error, '解除屏蔽失败'))
  }
}

async function saveProfile() {
  if (singleLevelLocation.value && form.location_province) {
    form.location_city = form.location_province
  }
  if (singleLevelHometown.value && form.hometown_province) {
    form.hometown_city = form.hometown_province
  }
  const requiredFields = [
    ['nickname', '请填写昵称'],
    ['phone', '请填写手机号'],
    ['email', '请填写邮箱'],
    ['birth_date', '请选择生日'],
    ['grade', '请填写年级'],
    ['school', '请填写学校'],
    ['location_province', '请选择所在省份'],
    ['location_city', '请选择所在城市'],
    ['hometown_province', '请选择家乡省份'],
    ['hometown_city', '请选择家乡城市'],
  ]
  const missing = requiredFields.find(([field]) => !String(form[field] || '').trim())
  if (missing) {
    ElMessage.warning(missing[1])
    return
  }
  saving.value = true
  try {
    const { data } = await api.patch('/profile/me', form)
    auth.user = data
    fillForm(data)
    ElMessage.success('个人资料已保存')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    saving.value = false
  }
}

function selectAvatar(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 2 * 1024 * 1024) {
    ElMessage.error('请选择不超过 2MB 的 JPG 或 PNG 图片')
    return
  }
  cropFile.value = file
  cropperVisible.value = true
}

async function uploadAvatar(file) {
  uploading.value = true
  const body = new FormData()
  body.append('avatar', file)
  try {
    const { data } = await api.post('/profile/avatar', body)
    auth.user = data
    ElMessage.success('头像更新啦')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    uploading.value = false
  }
}

async function uploadRealPhotos(event) {
  const files = Array.from(event.target.files || [])
  if (!files.length) return
  if (files.some((file) => !['image/jpeg', 'image/png'].includes(file.type) || file.size > 5 * 1024 * 1024)) {
    ElMessage.error('真实照片仅支持不超过 5MB 的 JPG 或 PNG')
    event.target.value = ''
    return
  }
  uploadingReal.value = true
  const body = new FormData()
  files.forEach((file) => body.append('photos', file))
  try {
    const { data } = await api.post('/profile/real-photos', body)
    auth.user = data
    ElMessage.success('真实照片已保存，满足条件后才会向配对对象公开')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  } finally {
    uploadingReal.value = false
    event.target.value = ''
  }
}

async function deleteRealPhoto(url) {
  try {
    const { data } = await api.delete('/profile/real-photos', { params: { url } })
    auth.user = data
    ElMessage.success('照片已删除')
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function changePassword() {
  try {
    await api.post('/profile/change-password', passwordForm)
    ElMessage.success('密码已修改，请记住新密码')
    passwordDialog.value = false
    passwordForm.current_password = ''
    passwordForm.new_password = ''
  } catch (error) {
    ElMessage.error(errorMessage(error))
  }
}

async function logout() {
  await auth.logout()
  router.replace('/auth')
}

onMounted(() => load().catch((error) => ElMessage.error(errorMessage(error))))
</script>

<template>
  <AppShell>
    <section class="profile-page">
      <header class="page-intro compact"><div><p class="eyebrow">我的校园名片</p><h1>把真实的你，<span>认真写下来</span></h1></div></header>
      <div class="profile-layout">
        <aside class="identity-card">
          <div class="avatar-editor">
            <AvatarBubble :src="auth.user?.avatar_url" :name="auth.user?.nickname" :size="126" />
            <label class="camera-button" :class="{ loading: uploading }" title="选择并裁剪头像"><el-icon><Camera /></el-icon><input type="file" accept="image/jpeg,image/png" @change="selectAvatar" /></label>
          </div>
          <h2>{{ auth.user?.nickname }}</h2><p>{{ auth.user?.school || '学校待完善' }} · {{ auth.user?.grade }}<template v-if="auth.user?.department"> · {{ auth.user.department }}</template></p>
          <div class="completion-badge" :class="{ complete: auth.user?.profile_complete }">
            {{ auth.user?.profile_complete ? '✓ 已具备匹配资格' : `还需完善：${auth.user?.missing_profile_fields?.join('、') || '资料'}` }}
          </div>
          <router-link class="deep-profile-card" :class="{ complete: questionnaireStatus?.completed }" to="/questionnaire">
            <span>{{ questionnaireStatus?.completed ? '✦' : '◌' }}</span>
            <p><b>{{ questionnaireStatus?.completed ? '深度匹配已启用' : '解锁深度匹配' }}</b><small>{{ questionnaireStatus?.completed ? '价值观问卷已完成，可参与深度适配精排' : `${questionnaireStatus?.answered_count || 0}/${questionnaireStatus?.total_questions || 26} 题 · 自愿填写` }}</small></p>
            <i>→</i>
          </router-link>
          <div class="identity-lines"><span><b>账号</b>{{ auth.user?.account }}</span><span><b>性别</b>{{ auth.user?.gender === 'male' ? '男生' : '女生' }}</span><span><b>年龄</b>{{ auth.user?.age }} 岁</span><span><b>身高</b>{{ auth.user?.height_cm ? `${auth.user.height_cm} cm` : '未填写' }}</span><span><b>体重</b>{{ auth.user?.weight_kg ? `${auth.user.weight_kg} kg` : '未填写' }}</span><span><b>学校</b>{{ auth.user?.school || '待完善' }}</span><span><b>专业/院系</b>{{ auth.user?.department || '未填写' }}</span><span><b>所在地</b>{{ auth.user?.location_province && auth.user?.location_city ? `${auth.user.location_province} · ${auth.user.location_city}` : '待完善' }}</span><span><b>家乡</b>{{ auth.user?.hometown_province && auth.user?.hometown_city ? `${auth.user.hometown_province} · ${auth.user.hometown_city}` : '待完善' }}</span></div>
          <p class="privacy-note">🛡️ 身高和体重属于公开资料，会显示在推荐卡片中。账号不会向其他用户公开；联系方式和真实照片只有在双方心动并连续聊天满7天后才会公开。</p>
          <button class="security-link" @click="passwordDialog = true"><el-icon><Lock /></el-icon> 修改密码</button>
          <button class="logout-link" @click="logout"><el-icon><SwitchButton /></el-icon> 退出登录</button>
        </aside>

        <div class="profile-form-card">
          <div class="section-title"><div><p>基本信息</p><h2>让对方更容易认识你</h2></div><span>带 * 为必填</span></div>
          <el-form label-position="top">
            <div class="form-grid">
              <el-form-item label="昵称 *"><el-input v-model="form.nickname" maxlength="40" /></el-form-item>
              <el-form-item label="真实姓名（可选，仅自己可见）"><el-input v-model="form.real_name" maxlength="40" placeholder="不会向其他用户公开" /></el-form-item>
              <el-form-item label="手机号 *"><el-input v-model="form.phone" /></el-form-item>
              <el-form-item label="邮箱 *"><el-input v-model="form.email" /></el-form-item>
              <el-form-item label="微信号（隐私信息）"><el-input v-model="form.wechat" placeholder="可选，解锁后才公开" /></el-form-item>
              <el-form-item label="生日 *"><el-date-picker v-model="form.birth_date" value-format="YYYY-MM-DD" type="date" /></el-form-item>
              <el-form-item label="年级 *"><el-input v-model="form.grade" placeholder="例如 大一、研二" /></el-form-item>
              <el-form-item label="学校 *"><el-input v-model="form.school" placeholder="请输入学校全称" /></el-form-item>
              <el-form-item label="专业/院系（可选）"><el-input v-model="form.department" placeholder="如 计算机学院·软件工程" /></el-form-item>
              <el-form-item label="身高（公开，可选）">
                <div class="metric-input"><el-input-number v-model="form.height_cm" :min="100" :max="250" :step="1" controls-position="right" placeholder="例如 175" /><span>cm</span></div>
              </el-form-item>
              <el-form-item label="体重（公开，可选）">
                <div class="metric-input"><el-input-number v-model="form.weight_kg" :min="30" :max="300" :step="0.5" :precision="1" controls-position="right" placeholder="例如 65.0" /><span>kg</span></div>
              </el-form-item>
              <div class="full-field location-field-row">
                <el-form-item label="当前所在省份 *">
                  <el-select v-model="form.location_province" filterable placeholder="请选择省份或地区">
                    <el-option v-for="province in PROVINCE_OPTIONS" :key="province" :label="province" :value="province" />
                  </el-select>
                </el-form-item>
                <el-form-item label="当前所在城市 *">
                  <el-input v-if="singleLevelLocation" :model-value="`${form.location_province}（无需再选城市）`" disabled />
                  <el-select v-else v-model="form.location_city" filterable :disabled="!form.location_province" :placeholder="form.location_province ? '请选择所在城市' : '请先选择所在省份'">
                    <el-option v-for="city in cityOptions" :key="city" :label="cityLabel(form.location_province, city)" :value="city" />
                  </el-select>
                </el-form-item>
              </div>
              <div class="full-field location-field-row">
                <el-form-item label="家乡省份 *">
                  <el-select v-model="form.hometown_province" filterable placeholder="请选择家乡省份或地区">
                    <el-option v-for="province in PROVINCE_OPTIONS" :key="province" :label="province" :value="province" />
                  </el-select>
                </el-form-item>
                <el-form-item label="家乡城市 *">
                  <el-input v-if="singleLevelHometown" :model-value="`${form.hometown_province}（无需再选城市）`" disabled />
                  <el-select v-else v-model="form.hometown_city" filterable :disabled="!form.hometown_province" :placeholder="form.hometown_province ? '请选择家乡城市' : '请先选择家乡省份'">
                    <el-option v-for="city in hometownCityOptions" :key="city" :label="cityLabel(form.hometown_province, city)" :value="city" />
                  </el-select>
                </el-form-item>
              </div>
              <el-form-item class="full-field" label="个人简介">
                <el-input v-model="form.bio" type="textarea" :rows="4" maxlength="200" placeholder="可以写最近在做的事、想认识怎样的人……" />
                <span class="char-count">{{ bioLength }}/200</span>
              </el-form-item>
            </div>
          </el-form>
          <div class="private-photo-section">
            <div class="section-title"><div><p>隐私资料</p><h2>真实照片（可选）</h2></div><span>{{ auth.user?.real_photos?.length || 0 }}/6</span></div>
            <p class="section-helper">这些照片不会出现在每周推荐卡片中，只有双向心动并连续聊天满7天后才会向对方公开。</p>
            <div class="real-photo-grid">
              <div v-for="photo in auth.user?.real_photos" :key="photo" class="real-photo-item"><img :src="photo" alt="我的真实照片" /><button type="button" aria-label="删除照片" @click="deleteRealPhoto(photo)">×</button></div>
              <label v-if="(auth.user?.real_photos?.length || 0) < 6" class="real-photo-upload" :class="{ loading: uploadingReal }"><span>＋</span><b>{{ uploadingReal ? '上传中' : '添加照片' }}</b><small>JPG/PNG · 单张5MB</small><input type="file" multiple accept="image/jpeg,image/png" @change="uploadRealPhotos" /></label>
            </div>
          </div>
          <div class="interest-section">
            <div class="section-title"><div><p>兴趣标签</p><h2>最多选择 12 个</h2></div><span>{{ form.interest_ids.length }}/12</span></div>
            <div class="interest-workbench">
              <div class="interest-tools">
                <el-input v-model="interestSearch" clearable :prefix-icon="Search" placeholder="搜索足球、科幻、古风、MOBA…" />
                <span :class="{ full: form.interest_ids.length >= 12 }">{{ form.interest_ids.length >= 12 ? '已达到选择上限' : '选择越具体，匹配越准确' }}</span>
              </div>

              <div class="interest-category-tabs" role="tablist" aria-label="兴趣分类">
                <button
                  v-for="category in interestCategories"
                  :key="category"
                  type="button"
                  role="tab"
                  :aria-selected="!interestSearch && activeInterestCategory === category"
                  :class="{ active: !interestSearch && activeInterestCategory === category }"
                  @click="selectInterestCategory(category)"
                >
                  <span>{{ interestCategoryMeta[category]?.emoji || '✨' }}</span>{{ category }}
                  <i v-if="categorySelectedCount(category)">{{ categorySelectedCount(category) }}</i>
                </button>
              </div>

              <div v-if="selectedInterests.length" class="selected-interest-shelf">
                <b>我的兴趣</b>
                <button v-for="item in selectedInterests" :key="item.id" type="button" :aria-label="`移除${item.name}`" @click="removeInterest(item.id)">
                  {{ item.emoji }} {{ item.name }} <span>×</span>
                </button>
              </div>

              <div class="interest-channel-head">
                <span>{{ activeCategoryInfo.emoji }}</span>
                <div><b>{{ interestSearch ? '搜索结果' : activeInterestCategory }}</b><small>{{ activeCategoryInfo.description }}</small></div>
              </div>
              <el-checkbox-group v-if="visibleInterests.length" v-model="form.interest_ids" :max="12" class="interest-picker detailed">
                <el-checkbox-button v-for="item in visibleInterests" :key="item.id" :value="item.id">{{ item.emoji }} {{ item.name }}</el-checkbox-button>
              </el-checkbox-group>
              <div v-else class="interest-empty">没有找到相关标签，换个关键词试试。</div>
            </div>
          </div>
          <div class="blocked-users-section">
            <div class="section-title"><div><p>聊天安全</p><h2>已屏蔽用户</h2></div><span>{{ blockedUsers.length }} 人</span></div>
            <p class="section-helper">屏蔽期间不会收到对方消息，也不会再次匹配。解除屏蔽不会恢复已经结束的配对。</p>
            <div v-if="blockedUsers.length" class="blocked-user-list">
              <div v-for="item in blockedUsers" :key="item.id" class="blocked-user-item">
                <AvatarBubble :src="item.user.avatar_url" :name="item.user.nickname" :size="46" />
                <div><b>{{ item.user.nickname }}</b><small>{{ item.reason || '其他' }} · {{ blockedDate(item.created_at) }}</small></div>
                <button type="button" @click="unblockUser(item)">解除屏蔽</button>
              </div>
            </div>
            <div v-else class="blocked-empty">当前没有屏蔽任何用户。</div>
          </div>
          <div class="save-row"><span>基础资料完整后，才能开启每周匹配。</span><button class="primary-pill" :disabled="saving" @click="saveProfile">{{ saving ? '保存中…' : '保存资料' }}</button></div>
        </div>
      </div>
    </section>

    <el-dialog v-model="passwordDialog" title="修改密码" width="400px" align-center>
      <el-form label-position="top">
        <el-form-item label="当前密码"><el-input v-model="passwordForm.current_password" type="password" show-password /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="passwordForm.new_password" type="password" show-password placeholder="至少 8 位，含字母和数字" /></el-form-item>
      </el-form>
      <template #footer><button class="primary-pill full" @click="changePassword">确认修改</button></template>
    </el-dialog>

    <AvatarCropper v-model="cropperVisible" :file="cropFile" @confirm="uploadAvatar" />
  </AppShell>
</template>
